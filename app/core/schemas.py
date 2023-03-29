from marshmallow import fields

from .models import Point, Route, Employee, Address, Vehicle
from ..project.common import DefaultSQLAlchemyAutoSchema


class EmployeeSchema(DefaultSQLAlchemyAutoSchema):
    class Meta:
        model = Employee
        exclude = ('version',)

class VehicleSchema(DefaultSQLAlchemyAutoSchema):
    class Meta:
        model = Vehicle
        exclude = ('version',)

class AddressSchema(DefaultSQLAlchemyAutoSchema):
    class Meta:
        model = Address

class PointSchema(DefaultSQLAlchemyAutoSchema):
    address = fields.Nested(AddressSchema)

    class Meta:
        model = Point

class RouteSchema(DefaultSQLAlchemyAutoSchema):
    points = fields.Nested(PointSchema, many=True)

    class Meta:
        model = Route
        include_fk = True
        exclude = ('user_id',)