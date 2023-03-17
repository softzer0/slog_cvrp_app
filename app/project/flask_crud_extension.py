from flask import request, jsonify, abort, make_response, Blueprint, current_app
from flask.views import MethodView
from flask_jwt_extended import current_user, jwt_required
from marshmallow import Schema, fields
from sqlalchemy import inspect, or_

from app.project import db


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
                 filter_fields=None, sort_fields=None, custom_filters=None, custom_create_func=None,
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
        record = self.query.filter_by(id=record_id).first()
        if not record:
            abort(make_response(jsonify(msg="Record not found"), 404))
        return record

    def validate_required_fields(self, data):
        missing_fields = [field for field in self.required_fields if field not in data]

        if missing_fields:
            abort(make_response(jsonify(msg=f"Missing required fields: {', '.join(missing_fields)}"), 400))

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

        for field, column in self.sort_fields.items():
            if f"{field}_asc" in sort_by:
                query = query.order_by(column.asc())
            elif f"{field}_desc" in sort_by:
                query = query.order_by(column.desc())
        return query

    def apply_custom_filters(self, query):
        for custom_filter in self.custom_filters:
            query = custom_filter(query)
        return query

    @jwt_required()
    def get(self, record_id=None):
        if record_id is not None:
            # Get single record
            record = self.get_record_by_id(record_id)
            return self.schema().dump(record)
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
            records = query.paginate(page=page, per_page=per_page)
            return self.pagination_schema(self.schema).dump(records)

    @jwt_required()
    def post(self):
        data = request.get_json()
        data = {field: data[field] for field in self._all_fields if field in data}
        self.validate_required_fields(data)

        try:
            if not self.custom_create_func:
                record = self.model(user_id=current_user.id, **data)
                db.session.add(record)
                db.session.commit()
            else:
                record = self.custom_create_func(**data)
            return self.schema().dump(record), 201
        except Exception as e:
            return jsonify({'msg': str(e)}), 400

    @jwt_required()
    def put(self, record_id):
        data = request.get_json()
        record = self.get_record_by_id(record_id)
        for field in self.editable_fields:
            if field in data:
                setattr(record, field, data[field])
        try:
            db.session.commit()
            return self.schema().dump(record)
        except Exception as e:
            return jsonify({'msg': str(e)}), 400

    @jwt_required()
    def delete(self, record_id):
        record = self.get_record_by_id(record_id)
        db.session.delete(record)
        db.session.commit()
        return jsonify({'msg': f"{self.model.__name__} deleted successfully"})


def register_crud_routes(app, model, schema, editable_fields=None, required_fields=None, query=None, search_fields=None,
                         filter_fields=None, sort_fields=None, custom_filters=None, custom_create_func=None,
                         url_prefix=None, blueprint=None):
    if blueprint:
        bp = Blueprint(blueprint, __name__)
    else:
        bp = app

    view = CRUDView.as_view(
        model.__tablename__,
        model=model,
        schema=schema,
        editable_fields=editable_fields,
        required_fields=required_fields,
        query=query,
        search_fields=search_fields,
        filter_fields=filter_fields,
        sort_fields=sort_fields,
        custom_filters=custom_filters,
        custom_create_func=custom_create_func
    )

    prefix = url_prefix or f'/{model.__tablename__.lower()}'
    bp.add_url_rule(f'{prefix}', view_func=view, methods=['GET', 'POST'])
    bp.add_url_rule(f'{prefix}/<int:record_id>', view_func=view, methods=['GET', 'PUT', 'DELETE'])

    if blueprint:
        app.register_blueprint(bp)
