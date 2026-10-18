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
        details = {}
        for detail in schema.get('details', []):
            relation = model._meta.get_field(detail['name'])
            # The generated contract owns this relation; clients never supply model paths.
            child = relation.related_model
            for field in detail['fields']:
                if field['kind'] in {'integer', 'decimal'}:
                    details[f"{detail['name']}.{field['name']}"] = {
                        'group': detail['name'], 'field': field['name'], 'model': child,
                    }
        result[declaration.key] = {'label': schema['title'], 'resource': declaration.key,
            'dimensions': set(registered['dimensions']), 'metrics': {'id', *registered['metrics']},
            'filters': set(registered['filters']), 'model_class': model, 'service': service,
            'detail_metrics': details}
        result[declaration.key]['metrics'].update(details)
    return result


def source_specs():
    from .validators import DATA_SOURCES
    return {**generated_sources(), **DATA_SOURCES}


def source_model(key, spec):
    if 'model_class' in spec:
        return spec['model_class']
    from django.contrib.auth import get_user_model
    from apps.tasks.models import TaskRecord
    from apps.files.models import FileModel
    return {'users': get_user_model(), 'tasks': TaskRecord, 'files': FileModel}[key]


def field_types(key, spec):
    model = source_model(key, spec)
    types = {'DateField': 'date', 'DateTimeField': 'datetime', 'BooleanField': 'boolean',
             'DecimalField': 'decimal', 'IntegerField': 'integer', 'PositiveIntegerField': 'integer',
             'BigIntegerField': 'integer', 'PositiveBigIntegerField': 'integer'}
    result = {}
    for name in spec['dimensions'] | spec['metrics'] | spec['filters']:
        detail = spec.get('detail_metrics', {}).get(name)
        field = detail['model']._meta.get_field(detail['field']) if detail else model._meta.get_field(name)
        result[name] = types.get(field.get_internal_type(), 'text')
    return result


def permitted_fields(user, key, spec):
    if 'service' in spec:
        if not has_permission_code(user, key + ':read'):
            return set()
        from apps.permissions.field_permissions import business_allowed_fields
        declared = spec['dimensions'] | spec['metrics'] | spec['filters']
        permitted = business_allowed_fields(user, key, 'read')
        if permitted is None:
            return declared
        allowed = declared & (permitted | {'id', 'created_at', 'updated_at', 'approval_status'})
        # Child fields need both the detail section and the individual scalar grant.
        return {name for name in allowed if name not in spec.get('detail_metrics', {})
                or spec['detail_metrics'][name]['group'] in permitted}
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
