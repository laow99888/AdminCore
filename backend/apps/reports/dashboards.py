"""Bounded compositions of explicit single-source definitions; no SQL or joins."""
from copy import deepcopy
import re

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .services import authorize_definition, drill_down, execute_definition
from .sources import field_types, source_specs
from .validators import validate_definition, validate_filters, OPERATORS

KEY = re.compile(r'^[a-z][a-z0-9_]{0,31}$')


def checked_key(value):
    return isinstance(value, str) and KEY.fullmatch(value)


def validate_design(value):
    if not isinstance(value, dict) or 'widgets' not in value:
        return validate_definition(value)
    if set(value) != {'schema_version', 'widgets', 'filters', 'links'} or value['schema_version'] != 2 or type(value['schema_version']) is not int:
        raise ValidationError('看板定义必须使用 schema_version=2、widgets、filters 和 links')
    widgets = value['widgets']
    if not isinstance(widgets, list) or not 1 <= len(widgets) <= 8:
        raise ValidationError('看板必须包含一至八个组件')
    result = {}
    for widget in widgets:
        if (not isinstance(widget, dict) or set(widget) != {'key', 'title', 'span', 'definition'}
                or not checked_key(widget['key']) or widget['key'] in result
                or not isinstance(widget['title'], str) or not widget['title'].strip() or len(widget['title']) > 80
                or type(widget['span']) is not int or widget['span'] not in {6, 12}):
            raise ValidationError('看板组件编码、名称或宽度无效')
        result[widget['key']] = {**widget, 'definition': validate_definition(widget['definition'])}
    filters = value['filters']
    if not isinstance(filters, list) or len(filters) > 4:
        raise ValidationError('看板统一筛选最多四项')
    keys = set()
    for item in filters:
        if (not isinstance(item, dict) or set(item) != {'key', 'label', 'operator', 'value', 'bindings'}
                or not checked_key(item['key']) or item['key'] in keys
                or not isinstance(item['label'], str) or not item['label'].strip() or len(item['label']) > 80
                or not isinstance(item['operator'], str) or item['operator'] not in OPERATORS
                or not isinstance(item['bindings'], list) or not 1 <= len(item['bindings']) <= 8):
            raise ValidationError('看板统一筛选定义无效')
        keys.add(item['key'])
        seen, types = set(), set()
        for binding in item['bindings']:
            spec = binding_spec(binding, result)
            if binding['widget'] in seen:
                raise ValidationError('统一筛选不能重复绑定同一组件')
            seen.add(binding['widget'])
            source = result[binding['widget']]['definition']['data_source']
            types.add(field_types(source, spec)[binding['field']])
            validate_filters(spec, [{'field': binding['field'], 'operator': item['operator'], 'value': item['value']}])
        if len(types) != 1:
            raise ValidationError('统一筛选绑定字段的类型必须相同')
    links = value['links']
    if not isinstance(links, list) or len(links) > 8:
        raise ValidationError('看板联动最多八项')
    seen = set()
    for link in links:
        if not isinstance(link, dict) or set(link) != {'source', 'source_field', 'target', 'target_field'}:
            raise ValidationError('看板联动定义无效')
        source = result.get(link['source']) if isinstance(link['source'], str) else None
        spec = binding_spec({'widget': link['target'], 'field': link['target_field']}, result)
        if not source or link['source'] == link['target'] or not isinstance(link['source_field'], str):
            raise ValidationError('看板联动来源无效')
        dimension = next((x for x in source['definition']['dimensions'] if x['field'] == link['source_field']), None)
        source_types = field_types(source['definition']['data_source'], source_specs()[source['definition']['data_source']])
        target_source = result[link['target']]['definition']['data_source']
        # Date buckets need interval bindings, deliberately not implicit equality.
        if not dimension or source_types[link['source_field']] in {'date', 'datetime'} or source_types[link['source_field']] != field_types(target_source, spec)[link['target_field']]:
            raise ValidationError('联动仅支持类型相同的非日期维度与筛选字段')
        identity = (link['source'], link['source_field'], link['target'], link['target_field'])
        if identity in seen:
            raise ValidationError('看板联动不能重复')
        seen.add(identity)
    return {'schema_version': 2, 'widgets': list(result.values()), 'filters': deepcopy(filters), 'links': deepcopy(links)}


def binding_spec(binding, widgets):
    if (not isinstance(binding, dict) or set(binding) != {'widget', 'field'} or not isinstance(binding['widget'], str)
            or binding['widget'] not in widgets or not isinstance(binding['field'], str)):
        raise ValidationError('筛选绑定的组件或字段无效')
    spec = source_specs()[widgets[binding['widget']]['definition']['data_source']]
    if binding['field'] not in spec['filters']:
        raise ValidationError('筛选绑定字段不在白名单内')
    return spec


def prepare(user, design, options=None):
    design = validate_design(design)
    options = {} if options is None else options
    if not isinstance(options, dict) or set(options) - {'filters', 'selection'}:
        raise ValidationError('报表运行选项无效')
    if 'widgets' not in design:
        if options:
            raise ValidationError('单报表不接受看板运行选项')
        authorize_definition(user, design)
        return design, {'single': design}
    overrides = options.get('filters', {})
    if not isinstance(overrides, dict) or set(overrides) - {x['key'] for x in design['filters']}:
        raise ValidationError('未登记的统一筛选')
    definitions = {x['key']: deepcopy(x['definition']) for x in design['widgets']}
    for item in design['filters']:
        for binding in item['bindings']:
            definitions[binding['widget']]['filters'].append({'field': binding['field'], 'operator': item['operator'],
                                                            'value': overrides.get(item['key'], item['value'])})
    selection = options.get('selection')
    if selection is not None:
        if (not isinstance(selection, dict) or set(selection) != {'widget', 'field', 'value'}
                or not isinstance(selection['widget'], str) or not isinstance(selection['field'], str)):
            raise ValidationError('联动选择无效')
        links = [x for x in design['links'] if x['source'] == selection['widget'] and x['source_field'] == selection['field']]
        if not links or selection['value'] is None:
            raise ValidationError('联动选择未登记或为空')
        for link in links:
            definitions[link['target']]['filters'].append({'field': link['target_field'], 'operator': 'eq', 'value': selection['value']})
    # Validate and authorize every component before the first aggregate query.
    for key, definition in definitions.items():
        if len(definition['filters']) > 18:
            raise ValidationError('组合筛选过多')
        # Saved filters are limited to six; composed filters have a separate bounded budget.
        base = {**definition, 'filters': []}
        normalized = validate_definition(base)
        spec = source_specs()[normalized['data_source']]
        normalized['filters'] = validate_filters(spec, definition['filters'])
        if 'comparison' in normalized and any(item['field'] == normalized['comparison']['field'] for item in normalized['filters']):
            raise ValidationError('比较日期字段不能同时配置统一筛选或联动')
        authorize_definition(user, normalized)
        definitions[key] = normalized
    return design, definitions


def run_design(user, design, options=None):
    design, definitions = prepare(user, design, options)
    if 'widgets' not in design:
        return execute_definition(user, design)
    # Internal execution keeps composed filters separate from saved-definition limits.
    from .services import execute_prepared
    widgets = [{**{k: widget[k] for k in ('key', 'title', 'span')},
                'result': execute_prepared(user, definitions[widget['key']])} for widget in design['widgets']]
    return {'schema_version': 2, 'widgets': widgets, 'definition': design, 'generated_at': timezone.now().isoformat()}


def design_details(user, design, payload):
    if not isinstance(payload, dict) or set(payload) - {'widget', 'options', 'group', 'page', 'page_size'}:
        raise ValidationError('明细请求包含未登记属性')
    design, definitions = prepare(user, design, payload.get('options'))
    key = payload.get('widget', 'single')
    if not isinstance(key, str) or key not in definitions:
        raise ValidationError('明细组件未登记')
    return drill_down(user, definitions[key], payload.get('group', {}), payload.get('page', 1), payload.get('page_size', 20), prepared=True)
