"""邮箱归属及密码找回：数据库快照、一次消费、无凭据持久化。"""
import hashlib
import hmac
import re
import time
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import EmailMessage, get_connection
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import APIException, Throttled, ValidationError
from rest_framework.throttling import BaseThrottle

from apps.core.events import enqueue_event
from apps.logs.models import OperationLog
from .models import EmailChallenge
from .reauthentication import require_recent_password
from .sessions import request_ip

User = get_user_model()
INVALID_CODE = '确认凭据无效或已过期，请重新申请'
REQUEST_MESSAGE = '如果账户信息匹配且邮箱已验证，将发送密码重置邮件'


class RecoveryUnavailable(APIException):
    status_code = 503
    default_detail = '邮件服务暂不可用，请稍后重试'
    default_code = 'email_unavailable'


def recovery_enabled():
    # minimal 不启动 worker/beat/Redis，不能登记后假报“邮件已发”。
    return bool(settings.AUTH_EMAIL_ENABLED and settings.ADMINCORE_MODULES
                and settings.EMAIL_HOST and settings.DEFAULT_FROM_EMAIL)


def require_email_service():
    if not recovery_enabled():
        raise RecoveryUnavailable()


def limited_request(request, purpose, identity=''):
    """只信任部署配置指定的代理；缓存 add/incr 保证并发计数不丢失。"""
    now = time.time()
    counters = [('ip', BaseThrottle().get_ident(request), 20)]
    if identity:
        counters.append(('identity', identity, 5))
    try:
        for kind, value, limit in counters:
            digest = hashlib.sha256(str(value).encode()).hexdigest()
            key = f'auth-email:{purpose}:{kind}:{digest}:{int(now // 60)}'
            count = 1 if cache.add(key, 1, timeout=120) else cache.incr(key)
            if count > limit:
                raise Throttled(wait=60 - now % 60)
    except Throttled:
        raise
    except Exception:
        raise RecoveryUnavailable() from None


def password_digest(user):
    return hashlib.sha256(user.password.encode()).hexdigest()


def signing_key_digest():
    return salted_hmac('admincore.auth.email.key.v1', 'challenge-key-version', secret=settings.SECRET_KEY,
                       algorithm='sha256').hexdigest()


def challenge_code(challenge):
    snapshot = '|'.join([challenge.pk.hex, str(challenge.user_id), challenge.purpose,
                         challenge.email, str(challenge.session_version), challenge.password_digest,
                         challenge.expires_at.isoformat(), challenge.signing_key_digest])
    signature = salted_hmac('admincore.auth.email.v1', snapshot, secret=settings.SECRET_KEY,
                            algorithm='sha256').hexdigest()
    return f'{challenge.pk.hex}.{signature}'


def code_identifier(code):
    if not isinstance(code, str) or not re.fullmatch(r'[0-9a-f]{32}\.[0-9a-f]{64}', code):
        raise ValidationError({'code': [INVALID_CODE]})
    return UUID(hex=code[:32])


def challenge_valid(challenge, user):
    return (challenge is not None and user.is_active and challenge.user_id == user.pk
            and challenge.consumed_at is None and challenge.expires_at > timezone.now()
            and challenge.email == user.email.strip().casefold()
            and challenge.session_version == user.session_version
            and hmac.compare_digest(challenge.signing_key_digest, signing_key_digest())
            and hmac.compare_digest(challenge.password_digest, password_digest(user))
            and (challenge.purpose != 'reset' or user.email_verified))


def create_challenge(user, purpose, request):
    now = timezone.now()
    EmailChallenge.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True).update(consumed_at=now)
    challenge = EmailChallenge.objects.create(user=user, purpose=purpose, email=user.email.strip().casefold(),
        session_version=user.session_version, password_digest=password_digest(user), signing_key_digest=signing_key_digest(),
        expires_at=now + timedelta(minutes=10))
    enqueue_event('auth.email', f'auth.email:{challenge.pk}', {'challenge_id': str(challenge.pk)}, request=request)
    return challenge


@transaction.atomic
def request_reset(request, username, email):
    user = User.objects.select_for_update().filter(username=username).first()
    if user and user.is_active and user.email_verified and user.verified_email == email.strip().casefold():
        create_challenge(user, 'reset', request)


@transaction.atomic
def request_verification(request):
    user = User.objects.select_for_update().get(pk=request.user.pk)
    require_recent_password(request, user, 'email:verify')
    try:
        from django.core.validators import validate_email
        validate_email(user.email)
    except DjangoValidationError:
        raise ValidationError({'email': '请先保存有效邮箱'}) from None
    if user.email_verified:
        raise ValidationError({'email': '当前邮箱已验证'})
    if User.objects.filter(verified_email=user.email.strip().casefold()).exclude(pk=user.pk).exists():
        raise ValidationError({'email': '该邮箱无法用于当前账户，请更换邮箱'})
    create_challenge(user, 'verify', request)


def locked_challenge(code, purpose, expected_user=None):
    identifier = code_identifier(code)
    candidate = EmailChallenge.objects.filter(pk=identifier, purpose=purpose).values('user_id').first()
    if not candidate or (expected_user is not None and candidate['user_id'] != expected_user.pk):
        raise ValidationError({'code': [INVALID_CODE]})
    user = User.objects.select_for_update().filter(pk=candidate['user_id']).first()
    challenge = EmailChallenge.objects.select_for_update().filter(pk=identifier, purpose=purpose).first()
    if user is None or not challenge_valid(challenge, user) or not hmac.compare_digest(challenge_code(challenge), code):
        raise ValidationError({'code': [INVALID_CODE]})
    return user, challenge


@transaction.atomic
def confirm_verification(request, code):
    user, challenge = locked_challenge(code, 'verify', expected_user=request.user)
    from .sessions import locked_request_session
    locked_request_session(request, user)
    try:
        with transaction.atomic():
            user.verified_email = challenge.email
            user.profile_version += 1
            user.save(update_fields=['verified_email', 'profile_version', 'updated_at'])
    except IntegrityError:
        raise ValidationError({'code': [INVALID_CODE]}) from None
    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=['consumed_at'])
    audit(request, user, 'email_verified')
    return user


@transaction.atomic
def reset_password(request, code, new_password, new_password2):
    user, challenge = locked_challenge(code, 'reset')
    if new_password != new_password2:
        raise ValidationError({'new_password2': '两次输入的密码不一致'})
    if user.check_password(new_password):
        raise ValidationError({'new_password': '新密码不能与当前密码相同'})
    try:
        validate_password(new_password, user)
    except DjangoValidationError as exc:
        raise ValidationError({'new_password': exc.messages}) from None
    user.set_password(new_password)
    user.session_version += 1
    user.must_change_password = False
    user.save(update_fields=['password', 'session_version', 'must_change_password', 'updated_at'])
    from .models import TOTPDevice
    TOTPDevice.objects.filter(user=user).update(pending_secret='', pending_expires_at=None,
        pending_session_id=None, pending_password_digest='', pending_session_version=None)
    # 所有同用户待用挑战一起作废，避免 reset/verify 之间存在可复用能力。
    EmailChallenge.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=timezone.now())
    audit(request, user, 'password_recovered')


def audit(request, user, operation):
    OperationLog.objects.create(user=user, action='update', resource='auth_email', resource_id=str(user.pk),
        description=operation, ip_address=request_ip(request) or '0.0.0.0')


@transaction.atomic
def prepare_challenge(payload):
    """短事务复核 user→challenge 后冻结邮件，不在事务中连接 SMTP。"""
    if set(payload) != {'challenge_id'}:
        raise ValueError('invalid_email_event')
    try:
        identifier = UUID(str(payload['challenge_id']))
    except (ValueError, TypeError):
        raise ValueError('invalid_email_event') from None
    candidate = EmailChallenge.objects.filter(pk=identifier).values('user_id').first()
    if not candidate:
        return
    user = User.objects.select_for_update().filter(pk=candidate['user_id']).first()
    challenge = EmailChallenge.objects.select_for_update().filter(pk=identifier).first()
    if user is None or not challenge_valid(challenge, user):
        return
    require_email_service()
    title = 'AdminCore 邮箱验证' if challenge.purpose == 'verify' else 'AdminCore 密码找回'
    message = EmailMessage(title, f'请在 AdminCore 页面手动粘贴以下确认码（10 分钟内有效）：\n\n{challenge_code(challenge)}\n\n若非本人操作，请忽略此邮件。',
        settings.DEFAULT_FROM_EMAIL, [challenge.email], connection=get_connection(timeout=settings.EMAIL_TIMEOUT))
    return message


def deliver_challenge(payload):
    message = prepare_challenge(payload)
    if message is not None and message.send(fail_silently=False) != 1:
        raise RuntimeError('email_delivery_failed')
