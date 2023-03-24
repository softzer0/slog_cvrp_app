from functools import wraps
from io import TextIOWrapper, StringIO
from csv import Sniffer, DictReader
from dateutil.parser import parse

from flask import Blueprint, request, make_response, jsonify, abort
from flask_jwt_extended import jwt_required, current_user

from ..project import redis_client, db
from .common import check_if_import_status, check_if_execution_status, get_execution_key, create_status_object, \
    save_import_status, save_execution_status, get_unassigned_addresses
from .tasks import TaskStatus, add_new_address, read_import_data, prepare_and_run_VRP
from ..project.flask_crud_extension import register_crud_routes, CRUDView
from .schemas import RouteSchema, EmployeeSchema, AddressSchema, VehicleSchema
from .models import Address, Employee, Route, Point, Vehicle

core_bp = Blueprint('core', __name__)

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
        return jsonify({'msg': "No valid depot address ID provided. Can be either a query parameter 'depot_addr_id', or can be set on the user level"}), 400
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
    editable_fields=['first_name', 'last_name', 'email', 'work_hours'],
    search_fields=['first_name', 'last_name', 'email'],
    filter_fields=['work_hours'],
    sort_fields=['id', 'work_hours'],
)

register_crud_routes(
    core_bp,
    model=Vehicle,
    schema=VehicleSchema,
    editable_fields=['name', 'reg_plates', 'mileage'],
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
            abort(make_response(jsonify(msg=str(e)), 400))
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
                'done_date': lambda value: parse(value).replace(microsecond=0, tzinfo=None),
            }
        )

    def after_update(self, record, original_record):
        if record.employee_id != original_record.employee_id:
            if record.employee_id:
                new_employee = Employee.query.filter_by(user_id=current_user.id, id=record.employee_id).first()
                if new_employee:
                    new_employee.work_hours += round(record.duration / 3600)
                    new_employee.version += 1

            if original_record.employee_id:
                old_employee = Employee.query.filter_by(id=original_record.employee_id).first()
                if old_employee:
                    old_employee.work_hours -= round(original_record.duration / 3600)
                    old_employee.version += 1

        if record.vehicle_id != original_record.vehicle_id:
            if record.vehicle_id:
                new_vehicle = Vehicle.query.filter_by(user_id=current_user.id, id=record.vehicle_id).first()
                if new_vehicle:
                    new_vehicle.mileage += record.distance
                    new_vehicle.version += 1

            if original_record.vehicle_id:
                old_vehicle = Vehicle.query.filter_by(id=original_record.vehicle_id).first()
                if old_vehicle:
                    old_vehicle.mileage -= original_record.distance
                    old_vehicle.version += 1

register_crud_routes(core_bp, model=Route, view_class=RouteCRUDView)
