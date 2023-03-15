from functools import wraps
from io import TextIOWrapper, StringIO
from csv import Sniffer, DictReader
from dateutil.parser import parse

from flask import Blueprint, request, make_response, jsonify, abort
from flask_jwt_extended import jwt_required, current_user
from sqlalchemy.orm import joinedload

from app.project import redis_client
from .common import check_if_import_status, check_if_execution_status, get_execution_key, create_status_object, \
    save_import_status, save_execution_status, get_record_by_id, get_unassigned_addresses
from .tasks import TaskStatus, add_new_address, read_import_data, prepare_and_run_VRP
from ..project import db
from ..project.utils import validate_required_fields, get_pagination_info
from .schemas import RouteSchema, EmployeeSchema, PaginationSchema, AddressSchema
from .models import Address, Employee, Route, Point

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

@core_bp.route('/addresses', methods=['GET'])
@jwt_required()
def get_all_unassigned_addresses():
    page, per_page = get_pagination_info(request)
    search = request.args.get('search')
    capacity_filter = request.args.get('capacity_filter', type=int)
    sort_by = request.args.get('sort_by', 'id_desc')
    addresses = get_unassigned_addresses(current_user.id)
    if search:
        addresses = addresses.filter(Address.address.like(f'%{search}%'))
    if capacity_filter:
        addresses = addresses.filter(Address.capacity == capacity_filter)
    if 'id' in sort_by:
        id_order = 'asc' if 'id_asc' in sort_by else 'desc'
        addresses = addresses.order_by(Address.id.asc() if id_order == 'asc' else Address.id.desc())
    if 'capacity' in sort_by:
        capacity_order = 'asc' if 'capacity_asc' in sort_by else 'desc'
        addresses = addresses.order_by(Address.capacity.asc() if capacity_order == 'asc' else Address.capacity.desc())
    addresses = addresses.paginate(page=page, per_page=per_page)
    return PaginationSchema(AddressSchema).dump(addresses)

@core_bp.route('/addresses', methods=['POST'])
@jwt_required()
@validate_required_fields('address', 'capacity')
def create_address():
    try:
        address = add_new_address(current_user.id, request.json['address'], request.json['capacity'])
        return AddressSchema().dump(address), 201
    except Exception as e:
        return jsonify({'msg': str(e)}), 400

def get_address_record(address_id):
    address = get_record_by_id(current_user.id, Address, address_id)
    if not address:
        abort(make_response(jsonify(msg="Address not found"), 404))
    return address

@core_bp.route('/addresses/<int:address_id>', methods=['GET'])
@jwt_required()
def get_address(address_id):
    address = get_address_record(address_id)
    return AddressSchema().dump(address)

@core_bp.route('/addresses/<int:address_id>', methods=['PUT'])
@jwt_required()
@not_during_execution
def update_address(address_id):
    address = get_address_record(address_id)
    capacity = request.json.get('capacity')
    if capacity:
        address['capacity'] = capacity
        try:
            db.session.commit()
        except Exception as e:
            return jsonify({'msg': str(e)}), 400
    return AddressSchema().dump(address)

@core_bp.route('/addresses/<int:address_id>', methods=['DELETE'])
@jwt_required()
@not_during_execution
def delete_address(address_id):
    address = get_address_record(address_id)
    db.session.delete(address)
    db.session.commit()
    return jsonify({'msg': "Address deleted successfully"})


@core_bp.route('/employees', methods=['GET'])
@jwt_required()
def get_all_employees():
    page, per_page = get_pagination_info(request)
    search = request.args.get('search')
    work_hours_filter = request.args.get('work_hours_filter', type=int)
    sort_by = request.args.get('sort_by', 'id_desc')
    employees = Employee.query.filter_by(user_id=current_user.id)
    if search:
        employees = employees.filter((Employee.first_name.like(f'%{search}%')) | (Employee.last_name.like(f'%{search}%')))
    if work_hours_filter:
        employees = employees.filter(Employee.work_hours >= work_hours_filter)
    if 'id' in sort_by:
        id_order = 'asc' if 'id_asc' in sort_by else 'desc'
        employees = employees.order_by(Employee.id.asc() if id_order == 'asc' else Employee.id.desc())
    if 'work_hours' in sort_by:
        work_hours_order = 'asc' if 'work_hours_asc' in sort_by else 'desc'
        employees = employees.order_by(Employee.work_hours.asc() if work_hours_order == 'asc' else Employee.work_hours.desc())
    employees = employees.paginate(page=page, per_page=per_page)
    return PaginationSchema(EmployeeSchema).dump(employees)

@core_bp.route('/employees', methods=['POST'])
@jwt_required()
@validate_required_fields('first_name', 'last_name', 'work_hours')
def create_employee():
    try:
        employee = Employee(
            user_id=current_user.id,
            first_name=request.json['first_name'],
            last_name=request.json['last_name'],
            work_hours=request.json['work_hours']
        )
        db.session.add(employee)
        db.session.commit()
        return EmployeeSchema().dump(employee), 201
    except ValueError as e:
        return jsonify({'msg': str(e)}), 400

def get_employee_record(employee_id):
    employee = get_record_by_id(current_user.id, Employee, employee_id)
    if not employee:
        abort(make_response(jsonify(msg="Employee not found"), 404))
    return employee

@core_bp.route('/employees/<int:employee_id>', methods=['GET'])
@jwt_required()
def get_employee(employee_id):
    employee = get_employee_record(employee_id)
    return EmployeeSchema().dump(employee)

@core_bp.route('/employees/<int:employee_id>', methods=['PUT'])
@jwt_required()
@not_during_execution
def update_employee(employee_id):
    employee = get_employee_record(employee_id)
    for field in ('first_name', 'last_name', 'work_hours'):
        if field in request.json:
            setattr(employee, field, request.json[field])
    try:
        db.session.commit()
    except Exception as e:
        return jsonify({'msg': str(e)}), 400
    return EmployeeSchema().dump(employee)

@core_bp.route('/employees/<int:employee_id>', methods=['DELETE'])
@jwt_required()
@not_during_execution
def delete_employee(employee_id):
    employee = get_employee_record(employee_id)
    db.session.delete(employee)
    db.session.commit()
    return jsonify({'msg': "Employee deleted successfully"})


def get_employee_id_if_exists(request):
    employee_id = request.args.get('employee_id', type=int) if request.method == 'GET' else request.json.get('employee_id')
    if employee_id:
        employee_exists = db.session.query(Employee.query.filter_by(user_id=current_user.id, id=employee_id).exists()).scalar()
        if not employee_exists:
            abort(make_response(jsonify(msg="Employee not found"), 404))
    return employee_id

@core_bp.route('/routes', methods=['GET'])
@jwt_required()
def get_all_routes():
    page, per_page = get_pagination_info(request)
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    sort_by = request.args.get('sort_by', 'id_desc')
    routes = Route.query.filter_by(user_id=current_user.id)
    employee_id = get_employee_id_if_exists(request)
    if employee_id:
        routes = routes.filter_by(employee_id=employee_id)
    if start_time:
        routes = routes.filter(Route.done_date >= parse(start_time))
    if end_time:
        routes = routes.filter(Route.done_date <= parse(end_time))
    if 'id' in sort_by:
        id_order = 'asc' if 'id_asc' in sort_by else 'desc'
        routes = routes.order_by(Route.id.asc() if id_order == 'asc' else Route.id.desc())
    if 'done_date' in sort_by:
        done_date_order = 'asc' if 'done_date_asc' in sort_by else 'desc'
        routes = routes.order_by(Route.done_date.asc() if done_date_order == 'asc' else Route.done_date.desc())
    routes = routes.options(joinedload(Route.points).joinedload(Point.address)).paginate(page=page, per_page=per_page)
    return PaginationSchema(RouteSchema).dump(routes)

@core_bp.route('/routes/<int:route_id>', methods=['PUT'])
@jwt_required()
def update_route(route_id):
    route = get_record_by_id(current_user.id, Route, route_id)
    if not route:
        return jsonify({'msg': "Route not found"}), 404
    route.employee_id = get_employee_id_if_exists(request)
    db.session.commit()
    return RouteSchema().dump(route)
