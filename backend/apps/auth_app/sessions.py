"""JWT 会话的登记、校验和锁顺序：用户行 → 会话行。"""
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.db.models.functions import MD5, Upper
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from apps.logs.models import OperationLog
from .models import AuthSession
from apps.core.client_ip import request_ip

User = get_user_model()


class SessionRefreshToken(RefreshToken):
    @property
    def access_token(self):
        token = super().access_token
        token['exp'] = min(token['exp'], self['exp'])
        return token


def agent_hint(request):
    value = request.META.get('HTTP_USER_AGENT', '') if request else ''
    return ''.join(character for character in value if character.isprintable())[:256]


def idle_cutoff():
    return timezone.now() - timedelta(seconds=getattr(settings, 'AUTH_SESSION_IDLE_SECONDS', 1800))


def active_sessions():
    from apps.sso.sessions import filter_active_linked_sessions
    current = AuthSession.objects.filter(revoked_at__isnull=True, expires_at__gt=timezone.now(),
        last_seen_at__gt=idle_cutoff(), user__is_active=True,
        session_version=F('user__session_version'), password_hash=Upper(MD5('user__password')))
    return filter_active_linked_sessions(current)


def session_id(token):
    try:
        return UUID(str(token.get('sid', '')))
    except (ValueError, TypeError, AttributeError):
        raise AuthenticationFailed('登录凭据已撤销，请重新登录', code='session_revoked')


def validate_session(session, user, token):
    now = timezone.now()
    password_hash = get_md5_hash_password(user.password)
    if (session is None or not user.is_active or session.user_id != user.pk
            or session.revoked_at is not None or session.expires_at <= now
            or session.last_seen_at <= idle_cutoff()
            or token.get('session_version') != user.session_version
            or session.session_version != user.session_version
            or session.password_hash != password_hash or token.get('hash_password') != password_hash):
        raise AuthenticationFailed('登录凭据已撤销，请重新登录', code='session_revoked')
    from apps.sso.sessions import validate_linked_session
    validate_linked_session(session, user, token)
    return session


def check_request_session(token, user):
    session = validate_session(AuthSession.objects.filter(pk=session_id(token), user=user).first(), user, token)
    cutoff = timezone.now() - timedelta(seconds=getattr(settings, 'AUTH_SESSION_TOUCH_SECONDS', 60))
    # 单条条件更新避免每次请求写库；撤销不能被触碰复活。
    if session.last_seen_at <= cutoff:
        AuthSession.objects.filter(pk=session.pk, revoked_at__isnull=True, last_seen_at__lte=cutoff).update(last_seen_at=timezone.now())
    return session


def locked_request_session(request, actor):
    """调用者必须在 atomic 中已锁定 fresh actor。"""
    session = AuthSession.objects.select_for_update().filter(pk=session_id(request.auth), user=actor).first()
    return validate_session(session, actor, request.auth)


def audit_session(request, actor, operation, identifier):
    OperationLog.objects.create(user=actor, action='logout' if operation == 'logout' else 'update',
        resource='session', resource_id=str(identifier), description=operation,
        ip_address=request_ip(request) or '0.0.0.0')


@transaction.atomic
def issue_session(user, request=None):
    actor = User.objects.select_for_update().filter(pk=user.pk).first()
    if actor is None or not actor.is_active or actor.password != user.password or actor.session_version != user.session_version:
        raise AuthenticationFailed('登录凭据已撤销，请重新登录')
    token = SessionRefreshToken.for_user(actor)
    now = timezone.now()
    session = AuthSession.objects.create(user=actor, session_version=actor.session_version,
        password_hash=get_md5_hash_password(actor.password), refresh_jti=token['jti'],
        created_at=now, last_seen_at=now,
        expires_at=now + timedelta(seconds=getattr(settings, 'AUTH_SESSION_ABSOLUTE_SECONDS', 86400)),
        ip_address=request_ip(request) if request else None, user_agent=agent_hint(request))
    token['sid'] = str(session.pk)
    token['user_id'] = str(actor.pk)
    token['session_version'] = actor.session_version
    token['hash_password'] = session.password_hash
    token['username'] = actor.username
    token['email'] = actor.email
    token['exp'] = min(token['exp'], int(session.expires_at.timestamp()))
    # 黑名单仅依赖 jti；不持久化可直接使用的刷新凭据。
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    OutstandingToken.objects.filter(jti=token['jti']).update(token='')
    return token


@transaction.atomic
def logout_session(request):
    actor = User.objects.select_for_update().filter(pk=request.user.pk).first()
    if actor is None:
        raise AuthenticationFailed('登录凭据已撤销，请重新登录')
    session = locked_request_session(request, actor)
    session.revoked_at = timezone.now()
    session.save(update_fields=['revoked_at'])
    audit_session(request, actor, 'logout', session.pk)
