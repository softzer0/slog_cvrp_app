from os import environ
from celery import Celery
from flask_mail import Mail
from flask_redis import FlaskRedis
from flask_sqlalchemy import SQLAlchemy
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema

# redis_client_bin = FlaskRedis()

db = SQLAlchemy()

class DefaultSQLAlchemyAutoSchema(SQLAlchemyAutoSchema):
    def __init__(self, *args, **kwargs):
        self.opts.sqla_session = db.session
        self.opts.datetimeformat = '%Y-%m-%dT%H:%M:%S+00:00'
        super().__init__(*args, **kwargs)

redis_client = FlaskRedis(decode_responses=True)
mail = Mail()

_broker_uri = environ.get('CELERY_BROKER_URI')
celery = Celery(__name__, broker=_broker_uri, backend=_broker_uri)