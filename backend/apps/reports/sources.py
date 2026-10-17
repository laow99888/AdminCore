"""业务数据源只从源码登记的生成模块读取字段白名单。"""
from rest_framework.exceptions import NotFound
from apps.core.modules import module_enabled
from apps.permissions.permissions import has_permission_code


def generated_sources():
    from apps.core.modules import MODULES
    from apps.core.codegen.integrations import registered_module
    result = {}
    for declaration in MODULES:
        if not module_enabled(declaration.key):
            continue
        try:
            schema, model, service = registered_module(declaration.key)
        except NotFound:
            continue
        registered = schema.get('reports')
        if not registered:
            continue
        result[declaration.key] = {'label': schema['title'], 'resource': declaration.key,
            'dimensions': set(registered['dimensions']), 'metrics': {'id', *registered['metrics']},
            'filters': set(registered['filters']), 'model_class': model, 'service': service}
    return result


def source_specs():
    from .validators import DATA_SOURCES
    return {**generated_sources(), **DATA_SOURCES}


def permitted_fields(user, key, spec):
    if 'service' in spec:
        if not has_permission_code(user, key + ':read'):
            return set()
        return spec['dimensions'] | spec['metrics'] | spec['filters']
    from apps.permissions.field_permissions import allowed_fields
    return allowed_fields(user, spec['resource'], 'read')


def validate_business_filter(spec, item):
    from decimal import Decimal
    from django.core.exceptions import ValidationError as ModelValidationError
    from rest_framework.exceptions import ValidationError
    from apps.approvals.graph import scalar
    field = spec['model_class']._meta.get_field(item['field'])
    kind = field.get_internal_type()
    op, value = item['operator'], item['value']
    for val in value if op == 'in' else [value]:
        if kind == 'DecimalField':
            try:
                scalar('decimal', val)
                field.clean(Decimal(val), None)
            except (ModelValidationError, ValueError, TypeError):
                raise ValidationError('报表金额筛选必须为有效精度的十进制字符串') from None
        elif kind in {'IntegerField', 'PositiveIntegerField'}:
            try:
                scalar('integer', val)
                field.clean(val, None)
            except ModelValidationError:
                raise ValidationError('报表整数筛选值无效') from None
        elif kind == 'BooleanField':
            if type(val) is not bool or op not in {'eq', 'in'}:
                raise ValidationError('布尔筛选仅支持 eq/in 和布尔值')
        else:
            if not isinstance(val, str) or len(val) > 200:
                raise ValidationError('文本筛选值必须为最多200字符的文本')
            try:
                field.clean(val, None)
            except (ModelValidationError, ValueError, OverflowError):
                raise ValidationError('报表筛选值与登记字段不一致') from None
        if op == 'contains' and kind not in {'CharField', 'TextField'}:
            raise ValidationError('包含筛选只能用于文本字段')
