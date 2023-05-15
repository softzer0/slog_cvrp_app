from re import compile as re_compile

from sqlalchemy.orm import validates

from ..project.common import db

coords_regex = re_compile(r'^(\d{1,2}\.\d+),(\d{1,2}\.\d+)$')

class Address(db.Model):
    __tablename__ = 'addresses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', onupdate='CASCADE', ondelete='CASCADE'))
    address = db.Column(db.String(100), nullable=False)
    coords = db.Column(db.String(37), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    # unavailable_from = db.Column(db.DateTime)
    # unavailable_until = db.Column(db.DateTime)

    @validates('coords')
    def validate_coords(self, _key, coords):
        if not coords_regex.fullmatch(coords):
            raise ValueError("Coordinates are not valid")
        return coords

    # @validates('unavailable_until')
    # def validate_unavailable_until(self, _key, value):
    #     if value < self.unavailable_from:
    #         raise ValueError('unavailable_until must be after unavailable_from')
    #     return value

    def __init__(self, user_id, address, capacity, coords):
        self.user_id = user_id
        self.address = address
        self.capacity = capacity
        self.coords = coords

    def __repr__(self):
        return f'''<Address '{self.address}'>'''

class Employee(db.Model):
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', onupdate='CASCADE', ondelete='CASCADE'))
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(128), unique=True)
    work_hours = db.Column(db.Integer, nullable=False)
    allocated_hours = db.Column(db.Integer, nullable=False, default=0)

class Vehicle(db.Model):
    __tablename__ = 'vehicles'

    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', onupdate='CASCADE', ondelete='CASCADE'))
    name = db.Column(db.String(50), nullable=False)
    reg_plates = db.Column(db.String(15), unique=True, nullable=False)
    mileage = db.Column(db.Float, nullable=False)
    allocated_km = db.Column(db.Float, nullable=False, default=0)

class Route(db.Model):
    __tablename__ = 'routes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', onupdate='CASCADE', ondelete='CASCADE'))
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id', onupdate='CASCADE', ondelete='SET NULL'))
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id', onupdate='CASCADE', ondelete='SET NULL'))
    done_date = db.Column(db.DateTime)
    link = db.Column(db.Text)
    duration = db.Column(db.Integer)
    distance = db.Column(db.Integer)

    points = db.relationship('Point', cascade='save-update, delete-orphan, merge, delete')
    employee = db.relationship('Employee', foreign_keys='Route.employee_id')
    vehicle = db.relationship('Vehicle', foreign_keys='Route.vehicle_id')

    def __init__(self, user_id, link=None, duration=None, distance=None):
        self.user_id = user_id
        self.link = link
        self.duration = duration
        self.distance = distance

    def __repr__(self):
        return f'''<Route for user ID: {self.user_id}{', done @ '+self.done_date.isoformat() if self.done_date else ''}>'''

class Point(db.Model):
    __tablename__ = 'points'

    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id', onupdate='CASCADE', ondelete='CASCADE'), nullable=False)
    address_id = db.Column(db.Integer, db.ForeignKey('addresses.id', onupdate='CASCADE', ondelete='CASCADE'), nullable=False)
    position = db.Column(db.Integer, nullable=False)

    address = db.relationship('Address', foreign_keys=[address_id])

    def __init__(self, route_id, address_id, position):
        self.route_id = route_id
        self.address_id = address_id
        self.position = position

    def __repr__(self):
        return f'''<Point for route ID: {self.route_id}, position #{self.position}>'''
