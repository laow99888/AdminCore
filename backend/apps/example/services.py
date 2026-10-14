"""模型写入、授权/版本复核和审计在同一 SQL 事务内完成。"""
import hashlib
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, APIException
from apps.auth_app.sessions import locked_request_session
from apps.core.data_scope import scope_queryset
from apps.core.modules import module_enabled
from apps.logs.audit import write_audit
from apps.permissions.permissions import has_permission_code
from .models import WorkItem


class VersionConflict(APIException):
    status_code = 409
    default_detail = '记录已变化，请刷新后重试'


def visible(user):
    return scope_queryset(WorkItem.objects.select_related('creator'), user, 'example', 'creator_id', fallback='self')


def projection(row):
    return {'id': row.pk, 'status': row.status, 'priority': row.priority, 'creator_id': row.creator_id,
            'version': row.version, 'title_sha256': hashlib.sha256(row.title.encode()).hexdigest()}


@transaction.atomic
def mutate(request, action, values, identifier=None):
    if not module_enabled('example'):
        raise NotFound()
    actor = locked_actor(request, action)
    before = None
    if action == 'create':
        if values['version'] != 0:
            raise VersionConflict()
        row = WorkItem.objects.create(creator=actor, **{**values, 'version': 1})
        if not visible(actor).filter(pk=row.pk).exists():
            raise PermissionDenied('新记录不在当前数据范围内')
    else:
        row = visible(actor).select_for_update(of=('self',)).filter(pk=identifier).first()
        if row is None:
            raise NotFound()
        if values['version'] != row.version:
            raise VersionConflict()
        before = projection(row)
        if action == 'update':
            for key, value in values.items():
                if key != 'version':
                    setattr(row, key, value)
            row.version += 1
            row.save()
    after = None if action == 'delete' else projection(row)
    write_audit(request=request, actor=actor, resource='example', identifier=row.pk,
                action=action, before=before, after=after)
    if action == 'delete':
        row.delete()
        return None
    return row


def locked_actor(request, action):
    """必须在 atomic 内调用，锁顺序为用户、设备、幂等记录、业务行。"""
    actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if actor is None:
        raise AuthenticationFailed('登录凭据已撤销')
    if request.auth is not None:
        locked_request_session(request, actor)
    if actor.must_change_password or not has_permission_code(actor, 'example:' + action):
        raise PermissionDenied('没有示例工单操作权限')
    return actor
