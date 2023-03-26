import datetime

from flask import request, jsonify, make_response, Blueprint, current_app
from flask.views import MethodView
from flask_jwt_extended import current_user, jwt_required
from marshmallow import Schema, fields
from sqlalchemy import inspect, or_, String, Integer, Float, Boolean, DateTime, Date
from sqlalchemy.orm import make_transient
from sqlalchemy.orm.exc import StaleDataError

from . import db


type_mapping = {
    String: str,
    Integer: int,
    Float: float,
    Boolean: bool,
    DateTime: datetime.datetime,
    Date: datetime.date,
}


class CRUDError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def to_response(self):
        return make_response(jsonify(msg=self.message), self.status_code)


class PaginationSchema(Schema):
    page = fields.Integer()
    per_page = fields.Integer()
    total = fields.Integer()

    def __init__(self, item_schema, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_fields['items'] = fields.List(fields.Nested(item_schema))
        self.dump_fields['items'] = self.load_fields['items']


class CRUDView(MethodView):
    def __init__(self, model, schema, editable_fields=None, required_fields=None, query=None, search_fields=None,
                 filter_fields=None, sort_fields=None, field_parsers=None, custom_filters=None, custom_create_func=None,
                 pagination_schema=PaginationSchema):
        self.model = model
        self.schema = schema
        self.editable_fields = editable_fields or inspect(self.model).columns.keys()
        self.required_fields = required_fields or self._get_required_fields()
        self._all_fields = self.editable_fields + self.required_fields
        self._query = query
        self.search_fields = search_fields
        self.filter_fields = self._get_fields_as_dict(filter_fields) if filter_fields else None
        self.sort_fields = self._get_fields_as_dict(sort_fields) if sort_fields else None
        self.field_parsers = field_parsers or {}
        self.custom_filters = custom_filters or []
        self.custom_create_func = custom_create_func
        self.pagination_schema = pagination_schema

    @property
    def query(self):
        if self._query:
            return self._query() if callable(self._query) else self._query
        return self.model.query.filter_by(user_id=current_user.id)

    def _get_fields_as_dict(self, fields):
        return {field: getattr(self.model, field) for field in fields} if not isinstance(fields, dict) else fields

    def _get_required_fields(self):
        required_fields = []
        for column in inspect(self.model).columns:
            if not column.nullable and not column.primary_key:
                required_fields.append(column.name)
        return required_fields

    def get_record_by_id(self, record_id):
        record = self.query.filter(self.model.id == record_id).first()
        if not record:
            raise CRUDError("Record not found", 404)
        return record

    def validate_required_fields(self, data):
        missing_fields = [field for field in self.required_fields if field not in data]

        if missing_fields:
            raise CRUDError(f"Missing required fields: {', '.join(missing_fields)}", 400)

    def get_pagination_info(self):
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', current_app.config.get('PAGE_LIMIT', 30), type=int)
        return page, per_page

    def apply_search_filters(self, query):
        search = request.args.get('search')
        if search:
            filters = [getattr(self.model, field).like(f'%{search}%') for field in self.search_fields]
            query = query.filter(or_(*filters))
        return query

    def apply_filter_fields(self, query):
        for field, column in self.filter_fields.items():
            filter_value = request.args.get(field)
            if filter_value:
                query = query.filter(column == filter_value)
        return query

    def apply_sorting(self, query):
        sort_by = request.args.get('sort_by', 'id_desc')
        sort_values = sort_by.split(',')

        for field, column in self.sort_fields.items():
            if f"{field}_asc" in sort_values:
                query = query.order_by(column.asc())
            elif f"{field}_desc" in sort_values:
                query = query.order_by(column.desc())
        return query

    def apply_custom_filters(self, query):
        for custom_filter in self.custom_filters:
            query = custom_filter(query)
        return query

    def parse_and_validate_data(self, data):
        parsed_data = {}
        for field, value in data.items():
            if field in self.field_parsers:
                try:
                    parsed_data[field] = self.field_parsers[field](value)
                except Exception as e:
                    raise CRUDError(str(e), 400)
            else:
                parsed_data[field] = value

            model_field_type = getattr(self.model, field).type

            # Find the corresponding Python type for the model field type
            python_type = None
            for sqlalchemy_type, py_type in type_mapping.items():
                if isinstance(model_field_type, sqlalchemy_type):
                    python_type = py_type
                    break

            if python_type is None:
                raise CRUDError(f"Type mapping not found for field '{field}'", 400)

            if not isinstance(parsed_data[field], python_type):
                raise CRUDError(f"Invalid type for field '{field}'", 400)

        return parsed_data

    @jwt_required()
    def get(self, record_id=None):
        if record_id is not None:
            # Get single record
            record = self.get_record_by_id(record_id)
            self.before_get_single(record)
            response = self.schema().dump(record)
            self.after_get_single(record)
            return response
        else:
            # Get paginated list of records
            page, per_page = self.get_pagination_info()
            query = self.query
            if self.search_fields:
                query = self.apply_search_filters(query)
            if self.filter_fields:
                query = self.apply_filter_fields(query)
            if self.custom_filters:
                query = self.apply_custom_filters(query)
            if self.sort_fields:
                query = self.apply_sorting(query)
            self.before_get_paginated(query)
            records = query.paginate(page=page, per_page=per_page)
            response = self.pagination_schema(self.schema).dump(records)
            self.after_get_paginated(records)
            return response

    @jwt_required()
    def post(self):
        data = request.get_json()
        data = {field: data[field] for field in self._all_fields if field in data}
        self.validate_required_fields(data)
        data = self.parse_and_validate_data(data)

        try:
            self.before_create(data)
            if not self.custom_create_func:
                record = self.model(user_id=current_user.id, **data)
                db.session.add(record)
                db.session.commit()
            else:
                record = self.custom_create_func(**data)
            self.after_create(record)
            return self.schema().dump(record), 201
        except Exception as e:
            return jsonify({'msg': str(e)}), 400

    def _perform_before_update(self, record, data):
        # Create a new SQLAlchemy object that is a copy of the original record
        original_record = db.session.merge(record, load=False)
        make_transient(original_record)

        self.before_update(record, data)
        return original_record

    @jwt_required()
    def put(self, record_id):
        data = request.get_json()
        record = self.get_record_by_id(record_id)
        data = self.parse_and_validate_data(data)
        original_record = self._perform_before_update(record, data)
        for field in self.editable_fields:
            if field in data:
                setattr(record, field, data[field])
        while True:
            try:
                self.after_update(record, original_record)
                db.session.commit()
                break
            except StaleDataError:
                # In case of a conflict, reload the records and retry the update
                db.session.rollback()
                db.session.refresh(record)
                db.session.refresh(original_record)
            except Exception as e:
                return jsonify({'msg': str(e)}), 400
            return self.schema().dump(record)

    @jwt_required()
    def delete(self, record_id):
        record = self.get_record_by_id(record_id)
        self.before_delete(record)
        db.session.delete(record)
        db.session.commit()
        self.after_delete(record)
        return jsonify({'msg': f"{self.model.__name__} deleted successfully"})

    def before_request(self, *args, **kwargs):
        pass

    def after_request(self, response, *args, **kwargs):
        return response

    def dispatch_request(self, *args, **kwargs):
        self.before_request(*args, **kwargs)
        try:
            response = super().dispatch_request(**kwargs)
        except CRUDError as e:
            response = e.to_response()
        return self.after_request(response, *args, **kwargs)

    def before_create(self, data):
        pass

    def after_create(self, record):
        pass

    def before_update(self, record, data):
        pass

    def after_update(self, record, original_record):
        pass

    def before_delete(self, record):
        pass

    def after_delete(self, record):
        pass

    def before_get_single(self, record):
        pass

    def after_get_single(self, record):
        pass

    def before_get_paginated(self, query):
        pass

    def after_get_paginated(self, records):
        pass


def register_crud_routes(app, model=None, view_class=None, schema=None, editable_fields=None, required_fields=None,
                         query=None, search_fields=None, filter_fields=None, sort_fields=None, field_parsers=None,
                         custom_filters=None, custom_create_func=None, url_prefix=None, blueprint=None):
    if blueprint:
        bp = Blueprint(blueprint, __name__)
    else:
        bp = app

    if view_class:
        view = view_class.as_view(view_class.__name__.lower())
    else:
        view = CRUDView.as_view(
            model.__tablename__,
            model,
            schema,
            editable_fields=editable_fields,
            required_fields=required_fields,
            query=query,
            search_fields=search_fields,
            filter_fields=filter_fields,
            sort_fields=sort_fields,
            field_parsers=field_parsers,
            custom_filters=custom_filters,
            custom_create_func=custom_create_func
        )

    prefix = url_prefix or f'/{model.__tablename__.lower()}'
    bp.add_url_rule(f'{prefix}', view_func=view, methods=['GET', 'POST'])
    bp.add_url_rule(f'{prefix}/<int:record_id>', view_func=view, methods=['GET', 'PUT', 'DELETE'])

    if blueprint:
        app.register_blueprint(bp)
