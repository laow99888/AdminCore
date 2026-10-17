"""在线表单 V2：受限声明式协议；发布、预览与提交共用同一规范。"""
import json
import re
from datetime import datetime
from decimal import Decimal

from rest_framework.exceptions import ValidationError

from .validators import KEY_RE, FORBIDDEN_KEYS, validate_definition, validate_record

SCALARS = {'text', 'textarea', 'number', 'select', 'date', 'boolean', 'decimal', 'datetime', 'multiselect'}
BASE = {'key', 'label', 'type', 'required', 'default', 'options', 'min', 'max', 'max_length'}
EXTRA = {'section', 'span', 'help', 'placeholder', 'visible_when', 'required_when', 'scale',
         'fields', 'min_rows', 'max_rows', 'rules'}
OPS = {'eq', 'ne', 'in', 'empty', 'not_empty', 'lt', 'lte', 'gt', 'gte'}


def fail():
    raise ValidationError('表单 V2 配置无效，请检查字段、布局与规则')


def bounded(value):
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 131072:
            fail()
    except (ValueError, TypeError, RecursionError):
        fail()


def text(value, maximum=120, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        fail()
    return value


def decimal_value(raw, scale):
    if not isinstance(raw, str) or not re.fullmatch(r'-?[0-9]{1,18}(?:\.[0-9]{1,8})?', raw):
        raise ValidationError('金额必须为精确十进制文本且符合精度限制')
    value = Decimal(raw)
    if len(value.as_tuple().digits) > 18 or -value.as_tuple().exponent > scale:
        raise ValidationError('金额必须为精确十进制文本且符合精度限制')
    return value


def scalar(field, raw):
    kind = field['type']
    if kind == 'decimal':
        value = decimal_value(raw, field['scale'])
        if ('min' in field and value < Decimal(field['min'])) or ('max' in field and value > Decimal(field['max'])):
            raise ValidationError('数值超出范围')
        return format(value, f'.{field["scale"]}f')
    if kind == 'datetime':
        try:
            if not isinstance(raw, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])', raw):
                raise ValueError
            parsed = datetime.fromisoformat(raw)
            if parsed.utcoffset() is None:
                raise ValueError
        except ValueError:
            raise ValidationError('日期时间必须包含秒与时区') from None
        return raw
    if kind == 'multiselect':
        if not isinstance(raw, list) or len(raw) > 100 or any(not isinstance(item, str) or item not in field['options'] for item in raw) or len(set(raw)) != len(raw):
            raise ValidationError('选项无效')
        return raw
    return validate_record({'fields': [{**field, 'required': False}]}, {field['key']: raw})[field['key']]


def condition(value, previous):
    if not isinstance(value, list) or not 1 <= len(value) <= 5:
        fail()
    result = []
    for rule in value:
        if not isinstance(rule, dict) or set(rule) - {'field', 'op', 'value'}:
            fail()
        if not isinstance(rule.get('field'), str):
            fail()
        target = previous.get(rule.get('field'))
        op = rule.get('op')
        if target is None or target['type'] in {'detail', 'multiselect'} or not isinstance(op, str) or op not in OPS:
            fail()
        if op in {'lt', 'lte', 'gt', 'gte'} and target['type'] not in {'number', 'decimal', 'date', 'datetime'}:
            fail()
        row = {'field': target['key'], 'op': op}
        if op in {'empty', 'not_empty'}:
            if 'value' in rule:
                fail()
        else:
            values = rule.get('value') if op == 'in' else [rule.get('value')]
            if not isinstance(values, list) or not 1 <= len(values) <= 20:
                fail()
            if any(empty(item) for item in values):
                fail()
            row['value'] = [scalar(target, item) for item in values] if op == 'in' else scalar(target, values[0])
        result.append(row)
    return result


def rules(value, fields):
    if not isinstance(value, list) or len(value) > 20:
        fail()
    result = []
    lookup = {f['key']: f for f in fields}
    for rule in value:
        if not isinstance(rule, dict) or set(rule) != {'left', 'op', 'right', 'message'}:
            fail()
        if not all(isinstance(rule[name], str) for name in ('left', 'right', 'op')):
            fail()
        left, right = lookup.get(rule['left']), lookup.get(rule['right'])
        if left is None or right is None or left['key'] == right['key'] or left['type'] != right['type'] or left['type'] not in {'number', 'decimal', 'date', 'datetime'} or rule['op'] not in {'lt', 'lte', 'gt', 'gte', 'eq'}:
            fail()
        result.append({**rule, 'message': text(rule['message'], 200)})
    return result


def fields(value, sections, child=False):
    if not isinstance(value, list) or not 1 <= len(value) <= 50:
        fail()
    previous = {}
    result = []
    for field in value:
        if not isinstance(field, dict) or set(field) - BASE - EXTRA:
            fail()
        key, kind = field.get('key'), field.get('type')
        if not isinstance(key, str) or not KEY_RE.fullmatch(key) or key in previous or key in FORBIDDEN_KEYS or not isinstance(kind, str) or kind not in SCALARS | ({'detail'} if not child else set()):
            fail()
        if type(field.get('required', False)) is not bool:
            fail()
        row = {'key': key, 'label': text(field.get('label')), 'type': kind, 'required': field.get('required', False)}
        if kind in {'decimal', 'datetime', 'multiselect', 'detail'}:
            allowed = {'decimal': {'scale', 'min', 'max', 'default'}, 'datetime': {'default'},
                       'multiselect': {'options', 'default'}, 'detail': {'fields', 'min_rows', 'max_rows', 'rules'}}[kind]
            if set(field) & (BASE | EXTRA) - {'key', 'label', 'type', 'required', 'section', 'span', 'help', 'placeholder', 'visible_when', 'required_when'} - allowed:
                fail()
            if kind == 'decimal':
                scale = field.get('scale', 2)
                if type(scale) is not int or not 0 <= scale <= 8:
                    fail()
                row['scale'] = scale
                for bound in ('min', 'max'):
                    if bound in field:
                        row[bound] = format(decimal_value(field[bound], scale), 'f')
                if 'min' in row and 'max' in row and Decimal(row['min']) > Decimal(row['max']):
                    fail()
            elif kind == 'multiselect':
                row['options'] = validate_definition({'fields': [{'key': key, 'label': row['label'], 'type': 'select', 'options': field.get('options')}]})['fields'][0]['options']
            elif kind == 'detail':
                row['fields'] = fields(field.get('fields'), {}, True)
                minimum, maximum = field.get('min_rows', 0), field.get('max_rows', 50)
                if type(minimum) is not int or type(maximum) is not int or not 0 <= minimum <= maximum <= 100 or maximum < 1:
                    fail()
                row.update(min_rows=minimum, max_rows=maximum, rules=rules(field.get('rules', []), row['fields']))
        else:
            typed = {'text': {'max_length'}, 'textarea': {'max_length'}, 'number': {'min', 'max'}, 'select': {'options'}, 'date': set(), 'boolean': set()}
            if set(field) & {'min', 'max', 'options', 'max_length'} - typed[kind]:
                fail()
            row.update(validate_definition({'fields': [{k: v for k, v in field.items() if k in BASE}]})['fields'][0])
            if set(field) & {'scale', 'fields', 'min_rows', 'max_rows', 'rules'}:
                fail()
        if not child:
            section = field.get('section', '')
            if not isinstance(section, str) or section and section not in sections:
                fail()
            row['section'] = section
        elif 'section' in field:
            fail()
        span = field.get('span', 2 if kind in {'textarea', 'detail'} else 1)
        if type(span) is not int or span not in {1, 2}:
            fail()
        row['span'] = span
        for name in ('help', 'placeholder'):
            if name in field:
                row[name] = text(field[name], 500, True)
        for name in ('visible_when', 'required_when'):
            if name in field:
                row[name] = condition(field[name], previous)
        if 'default' in field:
            row['default'] = scalar(row, field['default'])
        previous[key] = row
        result.append(row)
    if sum(f['type'] == 'detail' for f in result) > 5:
        fail()
    return result


def normalize_definition(value):
    bounded(value)
    if type(value.get('schema_version')) is not int or value['schema_version'] != 2 or set(value) - {'schema_version', 'fields', 'sections', 'rules'}:
        fail()
    sections = value.get('sections', [])
    if not isinstance(sections, list) or len(sections) > 20:
        fail()
    seen = set()
    normalized = []
    for section in sections:
        if not isinstance(section, dict) or set(section) != {'key', 'title'}:
            fail()
        key = section['key']
        if not isinstance(key, str) or not KEY_RE.fullmatch(key) or key in seen or key in FORBIDDEN_KEYS:
            fail()
        seen.add(key)
        normalized.append({'key': key, 'title': text(section['title'])})
    result = fields(value.get('fields'), seen)
    return {'schema_version': 2, 'sections': normalized, 'fields': result, 'rules': rules(value.get('rules', []), result)}


def empty(value):
    return value is None or isinstance(value, str) and not value.strip() or value == []


def matches(conditions, data, definitions):
    lookup = {field['key']: field for field in definitions}
    for rule in conditions:
        raw, op = data.get(rule['field']), rule['op']
        expected = rule.get('value')
        if op in {'empty', 'not_empty'}:
            matched = empty(raw) if op == 'empty' else not empty(raw)
        else:
            convert = {'decimal': Decimal, 'datetime': datetime.fromisoformat}.get(lookup[rule['field']]['type'], lambda value: value)
            raw = convert(raw) if raw is not None else None
            expected = [convert(v) for v in expected] if op == 'in' else convert(expected)
            if op == 'in':
                matched = any(same(raw, value) for value in expected)
            elif op in {'eq', 'ne'}:
                matched = same(raw, expected) if op == 'eq' else not same(raw, expected)
            else:
                matched = compare(raw, op, expected) if raw is not None else False
        if not matched:
            return False
    return True


def same(left, right):
    compatible = type(left) is type(right) or type(left) in (int, float) and type(right) in (int, float)
    return compatible and left == right


def compare(left, op, right):
    return {'lt': left < right, 'lte': left <= right, 'gt': left > right, 'gte': left >= right, 'eq': left == right}[op]


def normalize_record(definition, data):
    bounded(data)
    return record_fields(definition['fields'], definition.get('rules', []), data)


def record_fields(definitions, comparisons, data):
    if not isinstance(data, dict):
        raise ValidationError('记录数据必须为对象')
    if set(data) - {field['key'] for field in definitions}:
        raise ValidationError('记录包含未登记字段')
    result, errors = {}, {}
    for field in definitions:
        key = field['key']
        if 'visible_when' in field and not matches(field['visible_when'], result, definitions):
            continue  # 隐藏字段（包括旧值和默认值）不参与持久化及后续条件。
        raw = data.get(key, field.get('default'))
        required = field['required'] or 'required_when' in field and matches(field['required_when'], result, definitions)
        if empty(raw):
            if required or field['type'] == 'detail' and field['min_rows'] > 0:
                errors[key] = '必填字段不能为空'
            continue
        try:
            if field['type'] == 'detail':
                if not isinstance(raw, list) or not max(field['min_rows'], 1 if required else 0) <= len(raw) <= field['max_rows']:
                    raise ValidationError('明细行数超出范围')
                rows, row_errors = [], {}
                for index, item in enumerate(raw):
                    try:
                        rows.append(record_fields(field['fields'], field['rules'], item))
                    except ValidationError as exc:
                        row_errors[str(index)] = exc.detail
                if row_errors:
                    raise ValidationError(row_errors)
                result[key] = rows
            else:
                result[key] = scalar(field, raw)
        except ValidationError as exc:
            errors[key] = exc.detail
    lookup = {field['key']: field for field in definitions}
    for rule in comparisons:
        if rule['left'] not in result or rule['right'] not in result:
            continue
        left, right = result[rule['left']], result[rule['right']]
        kind = lookup[rule['left']]['type']
        if kind == 'decimal':
            left, right = Decimal(left), Decimal(right)
        elif kind == 'datetime':
            left, right = datetime.fromisoformat(left), datetime.fromisoformat(right)
        if not compare(left, rule['op'], right):
            errors[rule['left']] = rule['message']
    if errors:
        raise ValidationError(errors)
    return result
