from marshmallow import fields

from ..core.schemas import AddressSchema
from ..project.common import DefaultSQLAlchemyAutoSchema
from .models import User

class UserSchema(DefaultSQLAlchemyAutoSchema):
    depot_addr = fields.Nested(AddressSchema)

    class Meta:
        model = User
        exclude = ('password_hash', 'pass_last_changed')
