from distutils.util import strtobool
from functools import wraps

import flask
from flask import make_response, jsonify, current_app
from werkzeug.exceptions import abort


def get_bool_request_arg(request, name, throw_if_not_found=False):
    value = request.args.get(name, default='false' if not throw_if_not_found else None, type=str)
    if not value:
        abort(make_response(jsonify(msg=f"Required parameter '{name}' not provided"), 400))
    return bool(strtobool(value))

def append_to_list_in_dict(src, key, item):
    if key in src:
        src[key].append(item)
    else:
        src[key] = [item]

def validate_required_fields(*required_fields):
    def wrapper(fn):
        @wraps(fn)
        def decorated_function(*args, **kws):
            data = flask.request.get_json()
            if not data:
                flask.abort(make_response(jsonify(msg="No POST data provided"), 400))
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                flask.abort(make_response(jsonify(msg=f"Missing fields: {', '.join(missing_fields)}"), 400))
            return fn(*args, **kws)
        return decorated_function
    return wrapper

def get_pagination_info(request):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', current_app.config.get('PAGE_LIMIT', 30), type=int)
    return page, per_page
