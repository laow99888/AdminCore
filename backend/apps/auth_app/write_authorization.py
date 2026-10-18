"""事务内写入口授权；统一用户主键锁顺序，再检查原设备和当前权限。"""
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied


def authorize_write(request, code=None, *, admin=False, related_users=()):
    """调用方必须处于 atomic，且尚未锁业务行；相关用户也按 pk 一起锁定。"""
    from apps.permissions.permissions import has_permission_code
    if not connection.in_atomic_block:
        raise RuntimeError('Write authorization requires an atomic transaction')
    # PostgreSQL 的 NO KEY UPDATE 仍串行化用户授权变更，允许其他事务做用户外键检查。
    # FOR UPDATE 会与并发审批新增步骤的 KEY SHARE 相互等待，形成用户→申请→用户死锁。
    lock_options = {'no_key': True} if connection.features.has_select_for_no_key_update else {}
    rows = list(get_user_model().objects.select_for_update(**lock_options).filter(
        pk__in={request.user.pk, *related_users}).order_by('pk'))
    actor = next((row for row in rows if row.pk == request.user.pk), None)
    if actor is None or actor.is_service_account or not actor.is_active:
        raise AuthenticationFailed('登录凭据已撤销，请重新登录')
    if request.auth is not None:
        from .sessions import locked_request_session
        locked_request_session(request, actor)
    if (actor.must_change_password or (code is not None and not has_permission_code(actor, code))
            or (admin and not (actor.is_staff or actor.is_superuser))):
        raise PermissionDenied()
    request.user = actor
    return actor
