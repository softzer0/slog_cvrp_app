import json

from sqlalchemy import exists, select

from .models import Address, Point
from ..project import redis_client, db

get_import_key = lambda user_id: f'import-{user_id}'
get_execution_key = lambda user_id: f'execution-{user_id}'

def create_status_object(status, data=None):
    return {'status': status.value, 'data': data}

def _save_status(key, status, data):
    redis_client.set(key, json.dumps(create_status_object(status, data)))

def save_import_status(user_id, status, data=None):
    _save_status(get_import_key(user_id), status, data)

def save_execution_status(user_id, status, data=None):
    _save_status(get_execution_key(user_id), status, data)

def _check_if_status(key, status):
    result_str = redis_client.get(key)
    if not result_str:
        return False, None
    result = json.loads(result_str)
    return result.get('status') == status.value, result

def check_if_import_status(user_id, status):
    return _check_if_status(get_import_key(user_id), status)

def check_if_execution_status(user_id, status):
    return _check_if_status(get_execution_key(user_id), status)

def get_unassigned_addresses(user_id):
    return Address.query.outerjoin(Point).filter((Address.user_id == user_id) & (Point.address_id.is_(None)))

def is_address_assigned(user_id, address_id):
    return db.session.query(exists(select(Address.id).outerjoin(Point)).where((Address.user_id == user_id) &
        (Address.id == address_id) & (Point.id.isnot(None)))).scalar()
