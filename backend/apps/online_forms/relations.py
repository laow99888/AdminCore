"""表单业务关联只接受显式 V2 搜索登记的当前可读标题，不接受 ORM 路径。"""
from rest_framework.exceptions import ValidationError

from apps.core.business_search import sources


def resources(actor):
    for module, schema, service, _, fields, title in sources(actor):
        target = next((field for field in fields if field['name'] == title), None)
        if target:
            yield module.key, schema['title'], service, title, target['query']


def relation_queryset(resource, actor, tenant_id, lock=False):
    entry = next((item for item in resources(actor) if item[0] == resource), None)
    if entry is None:
        raise ValidationError('关联资源未登记、未启用或无读取权限')
    _, _, service, title, query = entry
    rows = service.visible(actor).filter(tenant_id=tenant_id)
    return (rows.select_for_update(of=('self',)) if lock else rows), title, query


def relation_values(definition, data):
    for field in definition.get('fields', []):
        key = field['key']
        if field['type'] == 'relation' and data.get(key):
            yield key, field, data[key]
        elif field['type'] == 'detail':
            for index, child in enumerate(data.get(key) or []):
                for path, target, value in relation_values(field, child):
                    yield f'{key}.{index}.{path}', target, value


def validate_relations(definition, data, actor, tenant_id, lock=False):
    # 对每个明确资源批量检查，并按资源/主键稳定排序获得行锁。
    values = list(relation_values(definition, data))
    for resource in sorted({field['resource'] for _, field, _ in values}):
        requested = {value for _, field, value in values if field['resource'] == resource}
        rows, _, _ = relation_queryset(resource, actor, tenant_id, lock)
        available = {str(row.pk) for row in rows.filter(pk__in=requested).order_by('pk')}
        if available != requested:
            raise ValidationError({path: '关联记录不可用或不在授权范围内' for path, field, value in values
                                   if field['resource'] == resource and value not in available})


def validate_relation_definition(definition, actor, tenant_id):
    for field in definition.get('fields', []):
        if field['type'] == 'relation':
            relation_queryset(field['resource'], actor, tenant_id)
        elif field['type'] == 'detail':
            validate_relation_definition(field, actor, tenant_id)
