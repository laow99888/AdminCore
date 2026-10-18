import hmac
import secrets
import time
from datetime import timedelta
from uuid import UUID

from cryptography.fernet import InvalidToken
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, Throttled, ValidationError

from apps.auth_app.models import AuthSession, TOTPDevice
from apps.auth_app.recovery import password_digest
from apps.auth_app.sessions import issue_session, request_ip, agent_hint
from apps.auth_app.totp import login_proof
from apps.core.modules import module_enabled
from apps.core.query_budget import query_budget
from apps.logs.models import LoginLog, OperationLog
from .configuration import SSOUnavailable, digest, provider
from .models import ExternalIdentity, LoginFlow, SSOSession
from .protocol import authorization_url, verified_subject

INVALID_FLOW = '企业登录确认已失效，请重新开始'
BROWSER_COOKIE = 'admincore_sso_browser'
COMPLETION_COOKIE = 'admincore_sso_completion'
COOKIE_PATH = '/api/v1/sso/'


def limited(request, purpose, identity=''):
    now = time.time()
    counters = [(request_ip(request) or 'unknown', 20)]
    if identity:
        counters.append((identity, 5))
    try:
        for value, maximum in counters:
            key = f'sso:{purpose}:{digest(value)}:{int(now // 60)}'
            count = 1 if cache.add(key, 1, timeout=120) else cache.incr(key)
            if count > maximum:
                raise Throttled(wait=60 - now % 60)
    except Throttled:
        raise
    except Exception:
        raise SSOUnavailable() from None


def require_origin(request, config):
    if request.headers.get('Origin') != config.frontend_origin or request.content_type.partition(';')[0] != 'application/json':
        raise PermissionDenied('请从本站企业登录页面发起请求')


def start(request, config, proof):
    from apps.auth_app.login_captcha import require_captcha
    limited(request, 'start')
    require_origin(request, config)
    require_captcha(request, '__oidc__', proof.get('captcha_id'), proof.get('captcha_code'))
    state, browser, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
    # A short-lived row is created only after the shared pre-auth rate/captcha checks.
    LoginFlow.objects.create(state_digest=digest(state), browser_digest=digest(browser),
        nonce_digest=digest(nonce), encrypted_verifier=config.cipher.encrypt(verifier.encode()).decode(),
        config_digest=config.fingerprint, expires_at=timezone.now() + timedelta(minutes=5))
    return authorization_url(config, state, nonce, verifier), browser


def consume_state(request, config):
    values = request.query_params
    if (set(values) - {'code', 'state', 'iss', 'error', 'error_description', 'error_uri', 'session_state'}
            or any(len(values.getlist(key)) != 1 for key in values)
            or not 20 <= len(values.get('state', '')) <= 128
            or len(values.get('code', '')) > 4096
            or ('iss' in values and values['iss'] != config.issuer)):
        raise AuthenticationFailed(INVALID_FLOW)
    browser = request.COOKIES.get(BROWSER_COOKIE, '')
    if not 20 <= len(browser) <= 128:
        raise AuthenticationFailed(INVALID_FLOW)
    with query_budget(), transaction.atomic():
        flow = LoginFlow.objects.select_for_update().filter(state_digest=digest(values['state'])).first()
        if (flow is None or flow.consumed_at or flow.expires_at <= timezone.now()
                or flow.config_digest != config.fingerprint or not hmac.compare_digest(flow.browser_digest, digest(browser))):
            raise AuthenticationFailed(INVALID_FLOW)
        encrypted = flow.encrypted_verifier
        flow.consumed_at = timezone.now()
        flow.encrypted_verifier = ''
        flow.save(update_fields=['consumed_at', 'encrypted_verifier'])
    # Consumption is committed before contacting the provider: even network failure cannot replay the callback.
    if values.get('error') or not values.get('code'):
        raise AuthenticationFailed('企业身份授权未完成，请重新开始')
    try:
        verifier = config.cipher.decrypt(encrypted.encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        raise SSOUnavailable() from None
    return flow, values['code'], verifier


def callback(request, config):
    limited(request, 'callback')
    flow, code, verifier = consume_state(request, config)
    subject = verified_subject(config, code, verifier, flow.nonce_digest)
    identity = ExternalIdentity.objects.select_related('user').filter(issuer=config.issuer, subject=subject, revoked_at__isnull=True).first()
    if identity is None or identity.user.is_service_account or not identity.user.is_active or identity.user.must_change_password or not identity.user.has_usable_password():
        audit_failure(request, 'unbound_or_inactive')
        raise AuthenticationFailed('企业身份未绑定或账号不可用，请联系管理员或使用本地登录')
    completion = secrets.token_urlsafe(32)
    with query_budget(), transaction.atomic():
        # User -> identity -> flow is the shared lock order for completion/unbinding.
        user = get_user_model().objects.select_for_update().get(pk=identity.user_id)
        identity = ExternalIdentity.objects.select_for_update().get(pk=identity.pk)
        flow = LoginFlow.objects.select_for_update().get(pk=flow.pk)
        if (not user.is_active or user.is_service_account or user.must_change_password or not user.has_usable_password() or identity.revoked_at
                or flow.expires_at <= timezone.now() or flow.completion_digest or not module_enabled('sso')
                or provider().fingerprint != config.fingerprint):
            raise AuthenticationFailed(INVALID_FLOW)
        flow.identity = identity
        flow.binding_version = identity.binding_version
        flow.password_digest, flow.session_version = password_digest(user), user.session_version
        flow.completion_digest = digest(completion)
        flow.expires_at = min(flow.expires_at, timezone.now() + timedelta(minutes=2))
        flow.save(update_fields=['identity', 'binding_version', 'password_digest', 'session_version', 'completion_digest', 'expires_at'])
    return f'{flow.pk}.{completion}'


def pending(request, config):
    cookie = request.COOKIES.get(COMPLETION_COOKIE, '')
    try:
        identifier, secret = cookie.split('.')
        identifier = UUID(identifier)
        if len(secret) != 43:
            raise ValueError()
    except (ValueError, AttributeError):
        raise AuthenticationFailed(INVALID_FLOW) from None
    flow = LoginFlow.objects.select_related('identity__user').filter(pk=identifier).first()
    if (flow is None or not flow.identity_id or flow.completed_at or flow.expires_at <= timezone.now()
            or flow.config_digest != config.fingerprint or not hmac.compare_digest(flow.completion_digest, digest(secret))):
        raise AuthenticationFailed(INVALID_FLOW)
    return flow


def current_identity(flow, user, identity):
    if (not user.is_active or user.is_service_account or user.must_change_password or not user.has_usable_password()
            or user.session_version != flow.session_version or password_digest(user) != flow.password_digest
            or identity.revoked_at or identity.binding_version != flow.binding_version):
        raise AuthenticationFailed(INVALID_FLOW)


def login_status(request, config):
    from apps.auth_app.login_captcha import issue_challenge
    limited(request, 'status')
    flow = pending(request, config)
    user = flow.identity.user
    current_identity(flow, user, flow.identity)
    return {'ready': True, 'mfa_required': TOTPDevice.objects.filter(user=user).exclude(active_secret='').exists(),
            'captcha': issue_challenge(request, user.username)}


def audit_failure(request, reason):
    # Closed server reasons only; never IdP response, query string, claims, sub or browser credentials.
    LoginLog.objects.create(username='[SSO]', status='failed', ip_address=request_ip(request) or '0.0.0.0',
                            user_agent=agent_hint(request), error_message='sso:' + reason)


def complete(request, config, values):
    from apps.auth_app.login_captcha import require_captcha, record_failure, record_success
    require_origin(request, config)
    flow = pending(request, config)
    limited(request, 'complete', str(flow.identity.user_id))
    try:
        with query_budget(), transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=flow.identity.user_id)
            identity = ExternalIdentity.objects.select_for_update().get(pk=flow.identity_id)
            flow = LoginFlow.objects.select_for_update().get(pk=flow.pk)
            if flow.completed_at or flow.expires_at <= timezone.now() or not module_enabled('sso') or provider().fingerprint != config.fingerprint:
                raise AuthenticationFailed(INVALID_FLOW)
            current_identity(flow, user, identity)
            require_captcha(request, user.username, values.get('captcha_id'), values.get('captcha_code'))
            login_proof(user, request, values.get('otp_code'))
            token = issue_session(user, request)
            session = AuthSession.objects.get(pk=token['sid'])
            session.expires_at = min(session.expires_at, timezone.now() + timedelta(seconds=config.session_seconds))
            session.save(update_fields=['expires_at'])
            SSOSession.objects.create(session=session, identity=identity, binding_version=identity.binding_version, config_digest=config.fingerprint)
            token['sso'] = True
            token['exp'] = min(token['exp'], int(session.expires_at.timestamp()))
            flow.completed_at = timezone.now()
            flow.completion_digest = ''
            flow.save(update_fields=['completed_at', 'completion_digest'])
            ip = request_ip(request) or '0.0.0.0'
            LoginLog.objects.create(user=user, username=user.username, status='success', ip_address=ip, user_agent=agent_hint(request))
            OperationLog.objects.create(user=user, action='login', resource='sso_identity', resource_id=str(identity.pk),
                                        description='企业身份与本地安全校验完成', ip_address=ip)
            get_user_model().objects.filter(pk=user.pk).update(login_count=F('login_count') + 1, last_login_ip=ip, last_login=timezone.now())
            record_success(request, user.username)
            return {'access': str(token.access_token), 'refresh': str(token), 'user': {
                'id': str(user.pk), 'username': user.username, 'email': user.email, 'avatar': user.avatar,
                'must_change_password': user.must_change_password}}
    except AuthenticationFailed as exc:
        code = exc.detail.get('code') if isinstance(exc.detail, dict) else None
        if code != 'mfa_required':
            record_failure(request, flow.identity.user.username)
            audit_failure(request, 'completion_rejected')
        raise
