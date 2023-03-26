from flask import request, Blueprint, current_app, render_template, make_response, jsonify, abort
from flask_jwt_extended import create_access_token, jwt_required, current_user, create_refresh_token, get_jwt_identity
from flask_mail import Message
from itsdangerous import TimestampSigner
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from .models import User
from .schemas import UserSchema
from ..core.models import Address, Point
from ..project.common import mail, db

user_bp = Blueprint('user', __name__, template_folder='templates')


# Create a route to authenticate your users and return JWTs. The
# create_access_token() function is used to actually generate the JWT.
@user_bp.route('/login', methods=['POST'])
def login():
    email = request.json.get('email', None)
    password = request.json.get('password', None)
    user = User.query.filter_by(email=email).first()
    if not user or not user.verify_password(password):
        return {'msg': "Bad email or password"}, 401

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)
    return {'access_token': access_token, 'refresh_token': refresh_token}

# We are using the `refresh=True` option in jwt_required to only allow
# refresh tokens to access this route.
@user_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return {'access_token': access_token}

# Protect a route with jwt_required, which will kick out requests
# without a valid JWT present.
@user_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    # We can now access our sqlalchemy User object via `current_user`.
    return UserSchema().dump(current_user)


def send_reset_password_mail(email, id):
    msg = Message("Password reset", sender=current_app.config['NO_REPLY_EMAIL'], recipients=[email])
    signer = TimestampSigner(current_app.config['SECRET_KEY'])
    msg.html = render_template('reset-password.html', token=signer.sign(str(id)).decode())
    mail.send(msg)

@user_bp.route('/create-user', methods=['POST'])
@jwt_required()
def create_user():
    if current_user.id != 1:
        return {'msg': "You're not allowed to do this"}, 403
    email = request.json.get('email', None)
    if not email:
        return {'msg': "No email provided"}, 400
    user = User(email=email, active=True)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {'msg': "User with specified email already exists"}, 400
    send_reset_password_mail(email, user.id)
    return {'id': current_user.id, 'email': current_user.email}

def check_password_reset_token(token):
    signer = TimestampSigner(current_app.config['SECRET_KEY'])
    try:
        id, timestamp = signer.unsign(token, max_age=86400, return_timestamp=True)
    except:
        abort(make_response(jsonify(msg="Expired or invalid token provided"), 401))
    user = User.query.filter_by(id=int(id)).first()
    if not user:
        abort(make_response(jsonify(msg="Targeted user doesn't exist"), 404))
    if user.pass_last_changed and user.pass_last_changed > timestamp.replace(tzinfo=None):
        abort(make_response(jsonify(msg="Password already reset, new token needed"), 400))
    return user

@user_bp.route('/reset-password/check/<token>', methods=['GET'])
def reset_password_check(token):
    check_password_reset_token(token)
    return {'msg': "OK"}

@user_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password(token):
    password = request.json.get('password', None)
    password_confirm = request.json.get('password', None)
    if not password:
        return {'msg': "No password provided"}, 400
    if password != password_confirm:
        return {'msg': "Password confirmation doesn't match with the provided password"}, 400
    result = check_password_reset_token(token)
    result.hash_password(password)
    result.pass_last_changed = datetime.utcnow()
    db.session.commit()
    return {'msg': "Password has been changed"}

@user_bp.route('/reset-password', methods=['POST'])
def reset_password_send():
    email = request.json.get('email', None)
    user = User.query.filter_by(email=email).first()
    if not user:
        return {'msg': "User with specified e-mail not found"}, 400
    send_reset_password_mail(email, user.id)
    return {'msg': "Reset password mail has been sent"}


@user_bp.route('/settings', methods=['PUT'])
@jwt_required()
def update_user_settings():
    if 'depot_addr_id' in request.json:
        depot_addr_id = request.json['depot_addr_id']
        if isinstance(depot_addr_id, int):
            if not db.session.query(exists(select(Address.id).outerjoin(Point)).where((Address.user_id == current_user.id) & (Address.id == depot_addr_id) & (Point.id == None))).scalar():
                return jsonify({'msg': "Unassigned address not found"}), 404
        else:
            return jsonify({'msg': "Invalid value for depot address ID"}), 404
        current_user.depot_addr_id = depot_addr_id
    if 'max_capacity' in request.json:
        max_capacity = request.json['max_capacity']
        if not isinstance(max_capacity, int) or max_capacity < 1:
            return jsonify({'msg': "Max capacity must be a number greater than 0"}), 400
        current_user.max_capacity = max_capacity
    if 'send_routes_to_employees' in request.json:
        send_routes_to_employees = request.json['send_routes_to_employees']
        if not isinstance(send_routes_to_employees, bool):
            return jsonify({'msg': "'send_routes_to_employees' must be a boolean value"}), 400
        current_user.send_routes_to_employees = send_routes_to_employees
    try:
        db.session.commit()
        return UserSchema().dump(current_user)
    except Exception as e:
        return jsonify({'msg': str(e)}), 400
