from distutils.util import strtobool

from flask import abort, make_response, jsonify, current_app, render_template
from flask_mail import Message

from .common import mail

def send_email(recipients, subject, template, **kwargs):
    msg = Message(subject, sender=current_app.config['FROM_EMAIL'], recipients=recipients)
    msg.html = render_template(template, **kwargs)
    mail.send(msg)

def get_bool_request_arg(request, name, throw_if_not_found=False):
    value = request.args.get(name, default='false' if not throw_if_not_found else None, type=str)
    if not value:
        abort(make_response(jsonify(msg=f"Required parameter '{name}' not provided"), 400))
    return bool(strtobool(value))