import copy
from flask import request
import logging
import functools
import yaml
from marshmallow import fields
from marshmallow.utils import _Missing
from .utils import FIELDS_JSON_TYPE_MAP, PYTHON_TYPE_JSON_TYPE_MAP, is_marsh_v3, data_schema, unpack

logger = logging.getLogger(__name__)


def swagger_decorator(
    path_schema=None, query_schema=None,
    form_schema=None, json_schema=None,
    headers_schema=None, response_schema=None,
    tags=None, max_length_log=None
):
    def decorator(func):

        def limit_log_length(content):
            current_content = copy.deepcopy(content)
            if max_length_log and len(current_content.__str__()) > max_length_log:
                current_content = current_content.__str__()
                return "%s...%s" % (
                    current_content[:int(max_length_log / 2)], current_content[-int(max_length_log / 2):])
            return current_content

        def log_format(content):
            content = limit_log_length(content)
            return content

        def parse_simple_schema(c_schema, location):
            ret = []
            for key, value in c_schema.__dict__.get('_declared_fields').items():
                values_real_types = list(set(FIELDS_JSON_TYPE_MAP) & set(value.__class__.__mro__))
                values_real_types.sort(key=value.__class__.__mro__.index)
                type_field = f'unsupported type {str(type(value))} (simple schema)'
                if values_real_types:
                    type_field = FIELDS_JSON_TYPE_MAP.get(values_real_types[0])
                if is_marsh_v3():
                    name = getattr(value, 'data_key', None) or key
                else:
                    name = getattr(value, 'load_from', None) or key
                tmp = {
                    'in': location,
                    'name': name,
                    'type': type_field,
                    'required': value.required if location != 'path' else True,
                    'description': value.metadata.get('doc', '')
                }
                if not isinstance(value.default, _Missing):
                    tmp['default'] = value.default
                ret.append(tmp)
            return ret

        def parse_json_schema(r_s):
            tmp = {}
            only = r_s.__dict__.get('only')
            for key, value in (r_s.__dict__.get('_declared_fields') or r_s.__dict__.get('declared_fields') or {}).items():
                if is_marsh_v3():
                    key = getattr(value, 'data_key', None) or key
                else:
                    key = getattr(value, 'load_from', None) or key
                if only and key not in only:
                    continue
                tmp[key] = {
                    'description': value.metadata.get('doc', '')
                }
                current = tmp[key]
                if isinstance(value, fields.Nested):
                    if value.many:
                        current['type'] = 'array'
                        current['items'] = {
                            'type': 'object',
                            'properties': parse_json_schema(value.schema),
                        }
                        continue

                    current['type'] = 'object'
                    current['properties'] = parse_json_schema(value.schema)
                    continue

                if isinstance(value, fields.List):
                    current['type'] = 'array'
                    current['items'] = {
                        'type': 'string',
                    }
                    if not isinstance(value.default, _Missing):
                        current['default'] = value.default
                    continue

                if value.metadata.get('type'):
                    current['type'] = PYTHON_TYPE_JSON_TYPE_MAP[value.metadata.get('type').__name__]
                    current['required'] = value.required
                    continue

                values_real_types = list(set(FIELDS_JSON_TYPE_MAP) & set(value.__class__.__mro__))
                values_real_types.sort(key=value.__class__.__mro__.index)
                if values_real_types:
                    current['type'] = FIELDS_JSON_TYPE_MAP.get(values_real_types[0])
                    current['required'] = value.required
                    continue

                current['default'] = value.default

            return tmp

        def parse_request_body_json_schema(c_schema):
            tmp = {
                'in': 'body',
                'name': 'body',
                'required': True,
                'description': 'json type of body',
                'schema': {
                    'properties': parse_json_schema(c_schema),
                    'type': 'object',
                }
            }
            return [tmp]

        def generate_doc():
            doc_dict = {}
            if path_schema or query_schema or form_schema or json_schema or headers_schema:
                doc_dict['parameters'] = []
            if path_schema:
                doc_dict['parameters'].extend(parse_simple_schema(path_schema, 'path'))
            if query_schema:
                doc_dict['parameters'].extend(parse_simple_schema(query_schema, 'query'))
            if form_schema:
                doc_dict['parameters'].extend(parse_simple_schema(form_schema, 'formData'))
            if headers_schema:
                doc_dict['parameters'].extend(parse_simple_schema(headers_schema, 'header'))
            if json_schema:
                doc_dict['parameters'].extend(parse_request_body_json_schema(json_schema))
            if response_schema:
                doc_dict['responses'] = {}
                for code, current_schema in response_schema.items():
                    current = parse_json_schema(current_schema)
                    # print(code, current)
                    # if current.type == 'unsupported type':
                    #     print('unsupported type')
                    #     continue
                    doc_dict['responses'][code] = {
                        'description': current_schema.__doc__,
                        'schema': {
                            'type': 'object',
                            "properties": current,
                        },
                    }
                    if not doc_dict['responses'][code].get('schema', {}).get('properties'):
                        doc_dict['responses'][code].update({'schema': None})
                    if getattr(current_schema.Meta, 'headers', None):
                        doc_dict['responses'][code].update(
                            {'headers': parse_json_schema(current_schema.Meta.headers)}
                        )
                    produces = getattr(current_schema.Meta, 'produces', None)
                    if produces:
                        doc_dict.setdefault('produces', [])
                        doc_dict['produces'].extend(produces)
                        ('application/xml' in produces and doc_dict['responses'][code]['schema'] and doc_dict
                            ['responses'][code]['schema']
                            .update({'xml': {'name': getattr(current_schema.Meta, 'xml_root', 'xml')}}))

            if tags:
                doc_dict['tags'] = tags

            ret_doc = """---\n""" + yaml.dump(doc_dict)
            return ret_doc

        func.__doc__ = (func.__doc__.strip() + generate_doc()) if func.__doc__ else generate_doc()

        @functools.wraps(func)
        def wrapper(*args, **kw):
            path_params = request.view_args
            query_params = request.args
            form_params = request.form
            json_params = request.get_json(silent=True) or {}
            header_params = request.headers
            logger.info(
                'request params\npath params: %s\nquery params: %s\nform params: %s\njson params: %s\n',
                log_format(path_params), log_format(query_params), log_format(form_params), log_format(json_params)
            )
            logger.info('headers: %s\n', header_params)
            request.path_schema, request.path_schema, request.form_schema = [None] * 3
            request.json_schema, request.headers_schema = [None] * 2
            try:
                path_schema and setattr(request, 'path_schema', data_schema(path_schema, path_params))
                query_schema and setattr(request, 'query_schema', data_schema(query_schema, query_params))
                form_schema and setattr(request, 'form_schema', data_schema(form_schema, form_params))
                json_schema and setattr(request, 'json_schema', data_schema(json_schema, json_params))
                headers_schema and setattr(request, 'headers_schema', data_schema(headers_schema, dict(header_params)))
            except Exception as e:
                if not hasattr(e, 'messages'):
                    return 'request error: %s' % e, 400
                return 'request error: %s' % ''.join(
                    [('%s: %s; ' % (x, ''.join(y))) for x, y in e.messages.items()]), 400
            f_result = func(*args, **kw)
            data, code, headers = unpack(f_result)
            logger.info('response data\ndata: %s\ncode: %s\nheaders: %s\n', log_format(data), code, headers)
            try:
                if response_schema and response_schema.get(code):
                    data = data_schema(response_schema.get(code), data)
                    r_headers_schema = getattr(response_schema.get(code).Meta, 'headers', None)
                    if r_headers_schema:
                        headers = data_schema(r_headers_schema, headers)
            except Exception as e:
                return 'response error: %s' % ''.join(
                    [('%s: %s; ' % (x, ''.join(y))) for x, y in e.messages.items()]), 400
            return data, code, headers

        return wrapper

    return decorator
