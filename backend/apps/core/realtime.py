"""只读快照与有界连接准入。SQL 锁顺序：用户 → 设备会话 → 全局预算。"""
from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework.exceptions import APIException, AuthenticationFailed, PermissionDenied

from apps.auth_app.authentication import SessionJWTAuthentication
from apps.auth_app.sessions import locked_request_session
from apps.core.data_scope import scope_queryset
from apps.core.models import RealtimeBudget, RealtimeLease
from apps.core.modules import module_enabled
from apps.permissions.permissions import has_permission_code

STREAM_SECONDS = 25
POLL_SECONDS = 5
LEASE_SECONDS = 35
MAX_CONNECTIONS = 100
MAX_USER_CONNECTIONS = 3


class ConnectionLimit(APIException):
    status_code = 429
    default_detail = '实时连接已达上限，请使用轮询'
    default_code = 'realtime_limit'


def authenticate(raw_token):
    if not module_enabled('realtime'):
        raise PermissionDenied('实时模块已关闭')
    authentication = SessionJWTAuthentication()
    token = authentication.get_validated_token(raw_token)
    user = authentication.get_user(token)
    if user.must_change_password:
        raise PermissionDenied('请先修改初始密码')
    return token, user


@transaction.atomic
def acquire(raw_token):
    token, current = authenticate(raw_token)
    user = get_user_model().objects.select_for_update().filter(pk=current.pk, is_active=True).first()
    if user is None:
        raise AuthenticationFailed('登录凭据已撤销')
    session = locked_request_session(SimpleNamespace(auth=token), user)
    if user.must_change_password:
        raise PermissionDenied('请先修改初始密码')
    # get_or_create 只用于迁移或恢复缺失的预算行，随后显式锁定。
    RealtimeBudget.objects.get_or_create(pk=1)
    RealtimeBudget.objects.select_for_update().get(pk=1)
    now = timezone.now()
    alive = RealtimeLease.objects.filter(expires_at__gt=now)
    if (alive.filter(session=session).exists() or alive.count() >= MAX_CONNECTIONS
            or alive.filter(session__user=user).count() >= MAX_USER_CONNECTIONS):
        raise ConnectionLimit()
    # 只替换本会话已过期的租约，不删除别的连接或任何业务记录。
    RealtimeLease.objects.filter(session=session).delete()
    return RealtimeLease.objects.create(session=session, expires_at=now + timedelta(seconds=LEASE_SECONDS)).pk


def release(identifier):
    # 旧连接的 finally 不能删掉同一会话之后新建的租约。
    RealtimeLease.objects.filter(pk=identifier).delete()


def _summary(queryset, **counts):
    values = queryset.aggregate(total=Count('pk'), changed_at=Max('updated_at'), **counts)
    for key, value in values.items():
        if hasattr(value, 'isoformat'):
            values[key] = value.isoformat()
    return values


def snapshot(raw_token, lease_id):
    """每次读取 fresh 身份/角色；无正文、邮箱、结果、原始错误或执行凭据。"""
    token, user = authenticate(raw_token)
    if not RealtimeLease.objects.filter(pk=lease_id, session_id=token['sid'], expires_at__gt=timezone.now()).exists():
        raise AuthenticationFailed('实时连接租约已失效')
    result = {}
    if module_enabled('notifications'):
        from apps.notifications.models import Notification
        result['notifications'] = _summary(Notification.objects.filter(recipient=user),
            unread_count=Count('pk', filter=Q(is_read=False)), read_at=Max('read_at'))
    if module_enabled('approvals'):
        from apps.approvals.models import ApprovalRequest
        result['approvals'] = _summary(ApprovalRequest.objects.filter(Q(applicant=user) | Q(assignee=user)),
            todo_count=Count('pk', filter=Q(assignee=user, status='pending')))
    if module_enabled('tasks') and has_permission_code(user, 'task:read'):
        from apps.tasks.models import TaskRecord
        records = scope_queryset(TaskRecord.objects.all(), user, 'task', 'creator_id')
        result['tasks'] = _summary(records, active_count=Count('pk', filter=Q(status__in=['pending', 'running'])))
        result['tasks']['active'] = [dict(id=str(row['id']), status=row['status'], progress=max(0, min(100, row['progress'])))
            for row in records.filter(status__in=['pending', 'running']).order_by('-updated_at', '-id')
            .values('id', 'status', 'progress')[:20]]
    return result
