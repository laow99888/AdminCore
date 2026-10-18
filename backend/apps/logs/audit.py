"""关键变更的显式投影；禁止直接序列化模型或记录请求体。"""
import json
import hashlib
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder

from .models import OperationLog
from apps.core.client_ip import request_ip

FIELDS = {
    'user': ('id', 'username', 'is_active', 'is_staff', 'is_superuser', 'must_change_password', 'session_version', 'profile_version', 'role_ids', 'group_ids', 'django_permission_ids'),
    'role': ('id', 'name', 'is_active', 'permission_ids'),
    'menu': ('id', 'name', 'path', 'icon', 'order', 'parent_id', 'permission_id', 'is_visible'),
    'permission': ('id', 'name', 'code', 'resource', 'action'),
    'user_role': ('id', 'user_id', 'role_id'),
    'user_profile': ('id', 'user_id', 'department', 'position'),
    'lifecycle': ('category', 'count', 'ids'),
    'list_view': ('id', 'module', 'owner_id', 'shared', 'version', 'definition_sha256'),
}

from apps.core.modules import MODULES
for module in MODULES:
    for resource, fields in module.audit_fields:
        if resource in FIELDS:
            raise ValueError('模块审计投影与核心资源冲突')
        FIELDS[resource] = fields


def project(resource, values):
    if values is None:
        return None
    if resource not in FIELDS or not isinstance(values, dict):
        raise ValueError('审计资源或投影未登记')
    values = dict(values)
    if resource == 'dictionary' and 'items' in values:
        values['items_count'] = len(values['items'])
    result = {key: values[key] for key in FIELDS[resource] if key in values}
    # 只接受显式资源投影；任意新增模型字段不会自动进入审计。
    result = json.loads(json.dumps(result, cls=DjangoJSONEncoder, ensure_ascii=False))
    if len(json.dumps(result, ensure_ascii=False).encode()) > 32 * 1024:
        raise ValueError('审计投影超过 32 KiB，请缩小变更范围')
    return result


def snapshot(resource, row):
    if row is None:
        return None
    values = {key: getattr(row, key) for key in FIELDS[resource] if hasattr(row, key)}
    if resource == 'user':
        values['role_ids'] = sorted(str(item.role_id) for item in row.roles.all())
        values['group_ids'] = sorted(str(item.pk) for item in row.groups.all())
        values['django_permission_ids'] = sorted(str(item.pk) for item in row.user_permissions.all())
    elif resource == 'role':
        values['permission_ids'] = sorted(str(item.permission_id) for item in row.permissions.all())
    elif resource == 'file':
        values['deleted_by'] = str(row.deleted_by_id) if row.deleted_by_id else None
    elif resource in ('announcement', 'notification'):
        values['content_length'] = len(row.content)
        values['content_sha256'] = hashlib.sha256(row.content.encode()).hexdigest()
    return project(resource, values)


def write_audit(*, resource, identifier='', action='update', request=None, actor=None,
                before=None, after=None, results=(), record=None, description='', status=200, origin=None):
    before, after = project(resource, before), project(resource, after)
    actor = actor or (request.user if request is not None and request.user.is_authenticated else None)
    rows = []
    for result in results:
        if len(rows) >= 1000:
            raise ValueError('批量审计最多 1000 项')
        rows.append({'id': str(UUID(str(result['id']))), 'status': int(result['status'])})
    request_id = (getattr(request, 'request_id', '') if request is not None else '') if origin is None else origin
    if record is not None and not request_id and origin is None:
        from apps.tasks.models import MaintenanceRequest, ImportExecution
        request_id = (MaintenanceRequest.objects.filter(record=record).values_list('request_id', flat=True).first()
                      or ImportExecution.objects.filter(record=record).values_list('request_id', flat=True).first() or '')
    actor_identifier = str(actor.pk) if actor else ''
    if actor is not None:
        from django.contrib.auth import get_user_model
        if not get_user_model().objects.filter(pk=actor.pk).exists():
            actor = None
    return OperationLog.objects.create(user=actor, actor_identifier=actor_identifier,
        action=action, resource=resource, resource_id=str(identifier),
        request_id=request_id, task_record_id=record.pk if record else None,
        task_id=record.celery_task_id if record else '', audit_version=1,
        before_values=before, after_values=after, batch_results=rows,
        description=description or json.dumps({'before': before, 'after': after}, ensure_ascii=False),
        status=status, ip_address=(request_ip(request) or '0.0.0.0') if request is not None else '127.0.0.1')
