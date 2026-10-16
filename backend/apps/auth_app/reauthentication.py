"""敏感操作仅在当前请求中核对密码；不签发可复用的确认凭据。"""
import hashlib
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from rest_framework.exceptions import APIException, AuthenticationFailed, PermissionDenied, Throttled, ValidationError

from .sessions import locked_request_session

PASSWORD_CONFIRMATION_SCOPES = frozenset({'session:revoke', 'session:revoke-others', 'session:admin-revoke-all', 'email:verify',
                                         'totp:setup', 'totp:enable', 'totp:disable', 'totp:recovery-codes',
                                         'user:sensitive-read', 'api_credential:create', 'api_credential:revoke',
                                         'sso:bind', 'sso:unbind', 'ip_policy:update'})


class PasswordConfirmationUnavailable(APIException):
    status_code = 503
    default_detail = '密码确认暂不可用，请稍后重试'
    default_code = 'password_confirmation_unavailable'


def require_recent_password(request, actor, scope):
    """调用者须在 atomic 中先锁用户，并保持事务至敏感操作完成。"""
    if scope not in PASSWORD_CONFIRMATION_SCOPES:
        raise ValueError('密码确认操作必须使用服务器定义的范围')
    if not connection.in_atomic_block:
        raise RuntimeError('密码确认必须与敏感操作处于同一事务')
    if request.user.pk != actor.pk:
        raise AuthenticationFailed('登录凭据已撤销，请重新登录', code='session_revoked')
    # 即使调用方误传旧对象，也不能使用旧密码确认新状态。
    actor = get_user_model().objects.select_for_update().filter(pk=actor.pk).first()
    if actor is None:
        raise AuthenticationFailed('登录凭据已撤销，请重新登录', code='session_revoked')
    session = locked_request_session(request, actor)
    if request.content_type.partition(';')[0].strip().lower() != 'application/json' or not isinstance(request.data, dict):
        raise ValidationError({'current_password': '请使用 JSON 提交当前密码'})
    password = request.data.get('current_password')
    if not isinstance(password, str) or not password or len(password) > 4096:
        raise ValidationError({'current_password': '请提供当前密码'})

    now = time.time()
    window = int(now // 60)
    retry_after = 60 - now % 60
    limits = (
        (f'user:{actor.pk}', getattr(settings, 'AUTH_REAUTH_USER_FAILURE_LIMIT', 10)),
        (f'scope:{actor.pk}:{scope}', getattr(settings, 'AUTH_REAUTH_SCOPE_FAILURE_LIMIT', 5)),
    )
    keys = [(f'password-confirmation:{hashlib.sha256(identity.encode()).hexdigest()}:{window}', limit)
            for identity, limit in limits]
    try:
        limited = any(cache.get(key, 0) >= limit for key, limit in keys)
    except Exception:
        raise PasswordConfirmationUnavailable() from None
    if limited:
        raise Throttled(wait=retry_after)
    if not actor.check_password(password):
        try:
            for key, _ in keys:
                if not cache.add(key, 1, timeout=120):
                    try:
                        cache.incr(key)
                    except ValueError:
                        # 计数键刚好过期时，从新时间窗的首个失败继续计数。
                        if not cache.add(key, 1, timeout=120):
                            cache.incr(key)
        except Exception:
            raise PasswordConfirmationUnavailable() from None
        raise PermissionDenied('当前密码不正确', code='password_confirmation_failed')
    return session
