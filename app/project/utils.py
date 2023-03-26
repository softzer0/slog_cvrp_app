from distutils.util import strtobool

from flask import abort, make_response, jsonify

def get_bool_request_arg(request, name, throw_if_not_found=False):
    value = request.args.get(name, default='false' if not throw_if_not_found else None, type=str)
    if not value:
        abort(make_response(jsonify(msg=f"Required parameter '{name}' not provided"), 400))
    return bool(strtobool(value))