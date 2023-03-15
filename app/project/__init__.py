# import logging
# from sys import stdout

# logging.basicConfig(
#     level=logging.DEBUG,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     handlers=[logging.StreamHandler(stdout)]
# )
# logging.getLogger('flask_cors').level = logging.DEBUG

from os import environ
from os.path import dirname, abspath

from flask import Flask
from flask_jwt_extended import JWTManager
from flask_cors import CORS

from .common import db, redis_client, mail  # , redis_client_bin
from ..user.models import User
from ..user import user_bp
from ..core import core_bp

def create_app():
    app = Flask(__name__, template_folder=f'{dirname(dirname(dirname(abspath(__file__))))}/templates')
    app.config.from_object(f'''app.project.config.{'DevelopmentConfig' if environ.get('FLASK_ENV', None) == 'development' else 'Config'}''')
    app.config.from_prefixed_env()

    CORS(app, supports_credentials=True)

    app.register_blueprint(user_bp)
    app.register_blueprint(core_bp)

    db.init_app(app)
    # redis_client_bin.init_app(app)
    redis_client.init_app(app)
    mail.init_app(app)

    jwt = JWTManager(app)
    # Register a callback function that loads a user from database whenever
    # a protected route is accessed. This should return any python object on a
    # successful lookup, or None if the lookup failed for any reason (for example
    # if the user has been deleted from the database).
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data['sub']
        return User.query.filter_by(id=identity).one_or_none()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run()