from passlib.apps import custom_app_context as pwd_context
from sqlalchemy import false, true

from ..project.common import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(128), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    pass_last_changed = db.Column(db.DateTime)
    active = db.Column(db.Boolean, server_default=false(), nullable=False)

    depot_addr_id = db.Column(db.Integer, db.ForeignKey('addresses.id', use_alter=True, onupdate='CASCADE', ondelete='SET NULL', name='user_address_fk'))
    max_capacity = db.Column(db.Integer, server_default='15', nullable=False)
    send_routes_to_employees = db.Column(db.Boolean, server_default=true(), nullable=False)

    depot_addr = db.relationship('Address', foreign_keys=[depot_addr_id])

    def hash_password(self, password):
        self.password_hash = pwd_context.encrypt(password)

    def verify_password(self, password):
        return pwd_context.verify(password, self.password_hash)

    def __init__(self, email, active=False):
        self.email = email
        self.active = active

    def __repr__(self):
        return f'''<User '{self.email}'>'''