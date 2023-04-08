from enum import Enum
from os import environ

from requests import get as requests_get
from sqlalchemy import exists, select

from .common import save_import_status, save_execution_status
from .engine.common import prepare_w_matrix, get_depot_and_genes
from .engine.cvrp import CVRP
from .engine.tabu import Tabu
from ..project.common import db, celery
from .models import Address, Route, Point

MAPBOX_API_KEY = environ.get('MAPBOX_API_KEY')

class TaskStatus(Enum):
    IDLE = 'idle'
    IN_PROGRESS = 'in_progress'
    DONE = 'done'
    ERROR = 'error'

def unassigned_address_w_coords_exists(user_id, coords):
    return db.session.query(exists(select(Address.id).outerjoin(Point)).where((Address.user_id == user_id) & (Address.coords == coords) & (Point.id == None))).scalar()

def add_new_address(user_id, address, capacity):
    response = requests_get('https://nominatim.openstreetmap.org/search/' + address + '?format=json').json()
    if not len(response):
        raise Exception("Given address doesn't exist")
    coords = response[0]['lat'] + ',' + response[0]['lon']
    if unassigned_address_w_coords_exists(user_id, coords):
        raise Exception("Unassigned address with the same coordinates already exists")
    address = Address(
        user_id=user_id,
        address=address,
        coords=coords,
        capacity=capacity
    )
    db.session.add(address)
    db.session.commit()
    return address

@celery.task()
def read_import_data(user_id, rows):
    invalid_addresses = []
    for row in rows:
        try:
            add_new_address(user_id, row['address'], row['capacity'])
        except:
            invalid_addresses.append(row['address'])
    save_import_status(user_id, TaskStatus.DONE, {'invalid_addresses': invalid_addresses})


def add_new_route(user_id, points, nodes, link, duration, distance):
    route = Route(user_id, link, duration, distance)
    db.session.add(route)
    db.session.commit()
    db.session.refresh(route)
    for i, p in enumerate(points):
        point = Point(route.id, nodes[p][0], i+1)
        db.session.add(point)

def create_link_and_add_route(user_id, res, coords, nodes):
    coordinates_string = ''
    link = 'https://s-log-directions.vercel.app/?depot='
    for i, p in enumerate(res):
        coords_txt = f'{coords[p][0]},{coords[p][1]}'
        coordinates_string += ';' + coords_txt
        if i < len(res) - 1:
            if i > 0:
                link += f'&point_{i}='
            link += coords_txt
            if i > 0:
                link += f',{nodes[p][1]}'
    response = requests_get('https://api.mapbox.com/directions/v5/mapbox/driving/' + coordinates_string[1:] + '?access_token=' + MAPBOX_API_KEY).json()
    r = response['routes'][0]
    add_new_route(user_id, res, nodes, link, r['duration'], r['distance'] / 1000)

VRP_INSTANCES = 2
@celery.task()
def prepare_and_run_VRP(user_id, depot_addr_id, max_capacity):
    try:
        coords, matrix, nodes = prepare_w_matrix(user_id, depot_addr_id)
        results = CVRP(max_capacity, matrix, nodes).start(VRP_INSTANCES)
        for res in results:
            create_link_and_add_route(user_id, res, coords, nodes)
        db.session.commit()
        save_execution_status(user_id, TaskStatus.DONE)
    except Exception as e:
        save_execution_status(user_id, TaskStatus.ERROR, {'msg': str(e)})

@celery.task()
def prepare_and_run_TSP(user_id, depot_addr_id):
    try:
        coords, matrix, nodes = prepare_w_matrix(user_id, depot_addr_id)
        depot, genes = get_depot_and_genes(nodes)
        create_link_and_add_route(user_id, Tabu(matrix, depot).execute(genes, 1000), nodes, coords)
        db.session.commit()
        save_execution_status(user_id, TaskStatus.DONE)
    except Exception as e:
        save_execution_status(user_id, TaskStatus.ERROR, {'msg': str(e)})
