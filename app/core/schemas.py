from marshmallow import fields, Schema

from .models import Point, Route, Employee, Address
from ..project.common import DefaultSQLAlchemyAutoSchema

class PaginationSchema(Schema):
    page = fields.Integer()
    per_page = fields.Integer()
    total = fields.Integer()

    def __init__(self, item_schema, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_fields['items'] = fields.List(fields.Nested(item_schema))
        self.dump_fields['items'] = self.load_fields['items']


class EmployeeSchema(DefaultSQLAlchemyAutoSchema):
    class Meta:
        model = Employee
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