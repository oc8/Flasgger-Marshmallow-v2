from marshmallow import fields
import marshmallow

FIELDS_JSON_TYPE_MAP = {
    fields.Nested: 'object',
    fields.Dict: 'object',
    fields.List: 'array',
    fields.String: 'string',
    fields.UUID: 'string',
    fields.Number: 'number',
    fields.Integer: 'number',
    fields.Decimal: 'number',
    fields.Boolean: 'boolean',
    fields.Float: 'number',
    fields.DateTime: 'string',
    fields.Time: 'string',
    fields.Date: 'string',
    fields.TimeDelta: 'number',
    fields.Url: 'string',
    fields.URL: 'string',
    fields.Email: 'string',
    fields.Str: 'string',
    fields.Bool: 'boolean',
    fields.Int: 'number',
}
if int(marshmallow.__version__.split('.')[0]) == 3:
    FIELDS_JSON_TYPE_MAP.update({
        fields.NaiveDateTime: 'string',
        fields.AwareDateTime: 'string',
        fields.Tuple: 'array',
    })
PYTHON_TYPE_JSON_TYPE_MAP = {
    'str': 'string',
    'int': 'number',
    'float': 'number',
    'bool': 'boolean',
    'list': 'array',
    'dict': 'object',
}


def convert_field_to_json_type(field):
    """
    Convert a Marshmallow field to its corresponding JSON type for Swagger.
    """
    base_type = type(field)
    return FIELDS_JSON_TYPE_MAP.get(base_type, 'string')


def is_marsh_v3():
    return int(marshmallow.__version__.split('.')[0]) == 3


def data_schema(schema, data):
    data = schema().load(data or {})
    if not is_marsh_v3():
        data = schema().dump(data.data).data
    else:
        data = schema().dump(data)
    return data


def unpack(value):
    """Return a three tuple of data, code, and headers"""
    if not isinstance(value, tuple):
        return value, 200, {}

    try:
        data, code, headers = value
        return data, code, headers
    except ValueError:
        pass

    try:
        data, code = value
        return data, code, {}
    except ValueError:
        pass

    return value, 200, {}
