import re
from rest_framework.exceptions import ValidationError

KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
FIELD_TYPES = {'text', 'textarea', 'number', 'select', 'date', 'boolean'}
FORBIDDEN_KEYS = {'__proto__', 'prototype', 'constructor', 'html', 'script', 'template', 'component', 'widget', 'sql', 'url'}


def _safe(value, depth=0):
    if depth > 4:
        raise ValidationError('表单配置嵌套层级过深')
    if isinstance(value, str):
        if len(value) > 2000 or '<script' in value.lower() or 'javascript:' in value.lower():
            raise ValidationError('表单配置包含不安全内容')
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValidationError('表单配置包含禁止字段')
            _safe(child, depth + 1)
    elif isinstance(value, list):
        if len(value) > 100:
            raise ValidationError('表单配置数组超出上限')
        for child in value:
            _safe(child, depth + 1)
    return value


def validate_definition(value):
    if not isinstance(value, dict) or set(value) - {'fields'} or not isinstance(value.get('fields'), list):
        raise ValidationError('表单定义必须只包含 fields 数组')
    fields = value['fields']
    if not 1 <= len(fields) <= 50:
        raise ValidationError('表单字段数量必须为1至50')
    seen = set()
    normalized = []
    for field in fields:
        if not isinstance(field, dict) or set(field) - {'key', 'label', 'type', 'required', 'default', 'options', 'min', 'max', 'max_length'}:
            raise ValidationError('字段配置包含未登记属性')
        key, label, kind = field.get('key'), field.get('label'), field.get('type')
        if not isinstance(key, str) or not KEY_RE.fullmatch(key) or key in seen:
            raise ValidationError('字段标识无效或重复')
        if not isinstance(label, str) or not 1 <= len(label) <= 120 or kind not in FIELD_TYPES:
            raise ValidationError('字段标签或类型无效')
        seen.add(key)
        row = {'key': key, 'label': label, 'type': kind, 'required': bool(field.get('required', False))}
        if 'default' in field:
            row['default'] = field['default']
        if kind == 'select':
            options = field.get('options')
            if not isinstance(options, list) or not 1 <= len(options) <= 100 or any(not isinstance(item, str) or not 1 <= len(item) <= 120 for item in options):
                raise ValidationError('下拉选项必须为1至100个短文本')
            if len(set(options)) != len(options):
                raise ValidationError('下拉选项不能重复')
            row['options'] = options
        if kind in {'text', 'textarea'}:
            maximum = field.get('max_length', 2000 if kind == 'textarea' else 500)
            if type(maximum) is not int or not 1 <= maximum <= 2000:
                raise ValidationError('文本长度上限无效')
            row['max_length'] = maximum
        if kind == 'number':
            for name in ('min', 'max'):
                if name in field and (type(field[name]) not in (int, float) or abs(field[name]) > 10**12):
                    raise ValidationError('数值范围无效')
            if 'min' in field and 'max' in field and field['min'] > field['max']:
                raise ValidationError('数值最小值不能大于最大值')
            for name in ('min', 'max'):
                if name in field:
                    row[name] = field[name]
        _safe(row)
        normalized.append(row)
    return {'fields': normalized}


def validate_record(definition, data):
    if not isinstance(data, dict):
        raise ValidationError('记录数据必须为对象')
    fields = {field['key']: field for field in definition['fields']}
    if set(data) - set(fields):
        raise ValidationError('记录包含未登记字段')
    result = {}
    for key, field in fields.items():
        if key not in data:
            if field.get('required'):
                raise ValidationError({key: '必填字段不能为空'})
            if 'default' in field:
                result[key] = field['default']
            continue
        raw = data[key]
        kind = field['type']
        if kind in {'text', 'textarea'}:
            if not isinstance(raw, str) or len(raw) > field['max_length']:
                raise ValidationError({key: '文本值无效或超出长度'})
        elif kind == 'number':
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValidationError({key: '数值无效'})
            if 'min' in field and raw < field['min'] or 'max' in field and raw > field['max']:
                raise ValidationError({key: '数值超出范围'})
        elif kind == 'select' and (not isinstance(raw, str) or raw not in field['options']):
            raise ValidationError({key: '选项无效'})
        elif kind == 'date' and (not isinstance(raw, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw)):
            raise ValidationError({key: '日期格式必须为 YYYY-MM-DD'})
        elif kind == 'boolean' and not isinstance(raw, bool):
            raise ValidationError({key: '布尔值无效'})
        result[key] = raw
    return result
