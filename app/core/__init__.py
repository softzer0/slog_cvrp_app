from datetime import timedelta
from functools import wraps
from io import TextIOWrapper, StringIO
from csv import Sniffer, DictReader
from dateutil.parser import parse

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, current_user

from ..project import redis_client, db
from .common import check_if_import_status, check_if_execution_status, get_execution_key, create_status_object, \
    save_import_status, save_execution_status, get_unassigned_addresses
from .tasks import TaskStatus, add_new_address, read_import_data, prepare_and_run_VRP, prepare_and_run_TSP
from ..project.flask_crud_extension import register_crud_routes, CRUDView, CRUDError
from .schemas import RouteSchema, EmployeeSchema, AddressSchema, VehicleSchema
from .models import Address, Employee, Route, Point, Vehicle
from ..project.utils import get_bool_request_arg, send_email

core_bp = Blueprint('core', __name__, template_folder='templates')

def return_err_if_in_progress(fn, check_f, msg):
    @wraps(fn)
    def decorated_function(*args, **kwargs):
        if check_f(current_user.id, TaskStatus.IN_PROGRESS)[0]:
            return {'msg': msg}, 400
        return fn(*args, **kwargs)
    return decorated_function

not_during_import = lambda fn: return_err_if_in_progress(fn, check_if_import_status, "Can't do this while import is already in progress")
not_during_execution = lambda fn: return_err_if_in_progress(fn, check_if_execution_status, "Can't do this while algorithm is being executed")

@core_bp.route('/import', methods=['POST'])
@jwt_required()
@not_during_import
def import_data():
    if request.files:
        csv_file = TextIOWrapper(request.files['file'].stream._file, 'UTF8', newline=None)
    else:
        data = request.form.get('data')
        if not data:
            return {'msg': "No import data provided"}, 400
        csv_file = StringIO(data)
    dialect = Sniffer().sniff(csv_file.read())
    csv_file.seek(0)
    rows = [line for line in DictReader(csv_file, ('address', 'capacity'), dialect=dialect)]
    read_import_data.delay(current_user.id, rows)
    save_import_status(current_user.id, TaskStatus.IN_PROGRESS)
    return {'msg': "Data has been parsed, please periodically query /get-import-state to check the status"}

def check_task_status(fn, get_key_fn=None):
    is_done, result = fn(current_user.id, TaskStatus.DONE)
    if get_key_fn and is_done:
        del redis_client[get_key_fn(current_user.id)]
    return result or create_status_object(TaskStatus.IDLE), 200 # 400 if result and result['data'] and 'msg' in result['data'] else 200

@core_bp.route('/get-import-state', methods=['GET'])
@jwt_required()
def check_import():
    return check_task_status(check_if_import_status)

@core_bp.route('/start-algorithm', methods=['POST'])
@jwt_required()
# @not_during_import
@not_during_execution
def start_algorithm():
    depot_addr_id = request.args.get('depot_addr_id', current_user.depot_addr_id, int)
    if not depot_addr_id:
        return jsonify({'msg': "No valid depot address ID provided - can be either a query parameter 'depot_addr_id', or can be set on the user level"}), 400
    if get_bool_request_arg(request, 'use_tsp'):
        prepare_and_run_TSP.delay(current_user.id, depot_addr_id)
    else:
        prepare_and_run_VRP.delay(current_user.id, depot_addr_id, current_user.max_capacity)
    save_execution_status(current_user.id, TaskStatus.IN_PROGRESS)
    return {'msg': "Algorithm execution has begun, please periodically query /get-execution-state to check the status"}

@core_bp.route('/get-execution-state', methods=['GET'])
@jwt_required()
def check_execution():
    return check_task_status(check_if_execution_status, get_execution_key)


register_crud_routes(
    core_bp,
    model=Address,
    schema=AddressSchema,
    editable_fields=['capacity'],
    required_fields=['address', 'capacity'],
    query=lambda: get_unassigned_addresses(current_user.id),
    search_fields=['address'],
    filter_fields={'capacity_filter': Address.capacity},
    sort_fields=['id', 'capacity'],
    custom_create_func=lambda address, capacity: add_new_address(current_user.id, address, capacity)
)

register_crud_routes(
    core_bp,
    model=Employee,
    schema=EmployeeSchema,
    editable_fields=['first_name', 'last_name', 'email', 'work_hours', 'allocated_hours'],
    search_fields=['first_name', 'last_name', 'email'],
    sort_fields=['id', 'work_hours'],
)

register_crud_routes(
    core_bp,
    model=Vehicle,
    schema=VehicleSchema,
    editable_fields=['name', 'reg_plates', 'mileage', 'allocated_km'],
    search_fields=['name', 'reg_plates'],
    sort_fields=['id', 'mileage'],
)

def date_range_filter(query):
    from_done_time = request.args.get('from_done_time')
    to_done_time = request.args.get('to_done_time')

    if from_done_time and to_done_time:
        try:
            query = query.filter(
                (Route.done_date >= parse(from_done_time)) &
                (Route.done_date <= parse(to_done_time))
            )
        except ValueError as e:
            raise CRUDError(e, 400)
    return query

class RouteCRUDView(CRUDView):
    def __init__(self):
        super().__init__(
            Route,
            RouteSchema,
            editable_fields=['employee_id', 'vehicle_id', 'done_date'],
            filter_fields=['employee_id', 'vehicle_id'],
            sort_fields=['id', 'done_date'],
            custom_filters=[date_range_filter],
            field_parsers={
                'done_date': lambda value: parse(value).replace(microsecond=0, tzinfo=None) if value is not None else None,
            }
        )

    def _send_email_if_employee_assigned(self, record, employee=None):
        if not employee:
            if not record.employee_id:
                return
            employee = Employee.query.get(record.employee_id)
        if not employee.email:
            return

        send_email([employee.email], "New Route Assigned", 'route.html', route_id=record.id, points=record.points, link=record.link,
                   duration=str(timedelta(seconds=record.duration)), distance=round(record.distance, 1))

    def _update_employee(self, employee, duration=None, no_allocate=False, to_work_hours=None):
        if to_work_hours or no_allocate:
            employee.work_hours += to_work_hours or duration
        if to_work_hours or not no_allocate:
            employee.allocated_hours += duration
        employee.version += 1

    def _update_vehicle(self, vehicle, distance, no_allocate=False, to_mileage=None):
        if to_mileage or no_allocate:
            vehicle.mileage += to_mileage or distance
        if to_mileage or not no_allocate:
            vehicle.allocated_km += distance
        vehicle.version += 1

    def after_update(self, record, original_record):
        is_done = bool(record.done_date)
        is_done_orig = bool(original_record.done_date)
        is_done_changed = (1 if is_done else -1) if is_done != is_done_orig else None

        if record.employee_id != original_record.employee_id:
            if record.employee_id:
                new_employee = Employee.query.filter_by(user_id=current_user.id, id=record.employee_id).first()
                if new_employee:
                    self._update_employee(new_employee, record.duration, is_done)
                    self._send_email_if_employee_assigned(record, new_employee)

            if original_record.employee_id:
                self._update_employee(db.session.get(Employee, original_record.employee_id), -original_record.duration, is_done_orig)

        elif record.employee_id and is_done_changed is not None:
            value = record.duration * is_done_changed
            self._update_employee(record.employee, -value, to_work_hours=value)

        if record.vehicle_id != original_record.vehicle_id:
            if record.vehicle_id:
                new_vehicle = Vehicle.query.filter_by(user_id=current_user.id, id=record.vehicle_id).first()
                if new_vehicle:
                    self._update_vehicle(new_vehicle, record.distance, is_done)

            if original_record.vehicle_id:
                self._update_vehicle(db.session.get(Vehicle, original_record.vehicle_id), -original_record.distance, is_done_orig)

        elif record.vehicle_id and is_done_changed is not None:
            value = record.distance * is_done_changed
            self._update_vehicle(record.vehicle_id, -value, to_mileage=value)

register_crud_routes(core_bp, model=Route, view_class=RouteCRUDView)
