"""RFC 6238 双因素：锁内消费计数/恢复码，不保存或记录明文密钥。"""
import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, AuthenticationFailed, ValidationError

from apps.logs.models import OperationLog
from .models import TOTPDevice
from .reauthentication import require_recent_password
from .recovery import limited_request, password_digest
from .sessions import issue_session, request_ip

User = get_user_model()


class TOTPUnavailable(APIException):
    status_code = 503
    default_detail = '双因素认证暂不可用，请联系管理员'
    default_code = 'mfa_unavailable'


def cipher():
    try:
        key = getattr(settings, 'AUTH_TOTP_ENCRYPTION_KEY', '')
        if not key:
            raise ValueError()
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError):
        raise TOTPUnavailable() from None


def available():
    try:
        cipher()
        return True
    except TOTPUnavailable:
        return False


def decrypt(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeError, ValueError):
        raise TOTPUnavailable() from None


def hotp(secret, counter, digits=6):
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff
    return str(value % (10 ** digits)).zfill(digits)


def recovery_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def consume_proof(device, value, *, allow_recovery=True, pending=False):
    secret = decrypt(device.pending_secret if pending else device.active_secret)
    if re.fullmatch(r'[0-9]{6}', value or ''):
        now_counter = int(time.time() // 30)
        for counter in (now_counter, now_counter - 1, now_counter + 1):
            if counter >= 0 and counter > device.last_counter and hmac.compare_digest(hotp(secret, counter), value):
                device.last_counter = counter
                return
    elif allow_recovery and re.fullmatch(r'[0-9a-f]{32}', value or ''):
        digest = recovery_hash(value)
        for index, stored in enumerate(device.recovery_hashes):
            if hmac.compare_digest(stored, digest):
                device.recovery_hashes = [*device.recovery_hashes[:index], *device.recovery_hashes[index + 1:]]
                return
    raise AuthenticationFailed({'detail': '认证码无效或已使用', 'code': 'mfa_invalid'})


def login_proof(user, request, value):
    device = TOTPDevice.objects.select_for_update().filter(user=user).first()
    if device is None or not device.active_secret:
        return
    cipher()
    if not value:
        raise AuthenticationFailed({'detail': '请输入动态认证码或恢复码', 'code': 'mfa_required'})
    limited_request(request, 'totp-login', str(user.pk))
    consume_proof(device, value)
    device.save(update_fields=['last_counter', 'recovery_hashes'])


def status(user):
    device = TOTPDevice.objects.filter(user=user).first()
    return {'enabled': bool(device and device.active_secret), 'available': available(),
            'recovery_codes_remaining': len(device.recovery_hashes) if device and device.active_secret else 0}


def actor_and_device(request, scope):
    user = User.objects.select_for_update().get(pk=request.user.pk)
    session = require_recent_password(request, user, scope)
    cipher()
    device, _ = TOTPDevice.objects.select_for_update().get_or_create(user=user)
    return user, session, device


def clear_pending(device):
    device.pending_secret = ''
    device.pending_expires_at = None
    device.pending_session_id = None
    device.pending_password_digest = ''
    device.pending_session_version = None


@transaction.atomic
def setup(request):
    user, session, device = actor_and_device(request, 'totp:setup')
    limited_request(request, 'totp-setup', str(user.pk))
    if device.active_secret:
        raise ValidationError('双因素认证已启用')
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    device.pending_secret = cipher().encrypt(secret.encode()).decode()
    device.pending_expires_at = timezone.now() + timedelta(minutes=10)
    device.pending_session_id = session.pk
    device.pending_password_digest = password_digest(user)
    device.pending_session_version = user.session_version
    device.last_counter = -1
    device.save()
    audit(request, user, 'totp_setup')
    uri = f'otpauth://totp/{quote("AdminCore:" + user.username, safe="")}?{urlencode({"secret": secret, "issuer": "AdminCore", "algorithm": "SHA1", "digits": 6, "period": 30})}'
    return {'secret': secret, 'otpauth_uri': uri, 'expires_at': device.pending_expires_at}


def new_recovery_codes(device):
    codes = [secrets.token_hex(16) for _ in range(10)]
    device.recovery_hashes = [recovery_hash(value) for value in codes]
    return codes


def audit(request, user, operation):
    OperationLog.objects.create(user=user, action='update', resource='totp', resource_id=str(user.pk),
        description=operation, ip_address=request_ip(request) or '0.0.0.0')


@transaction.atomic
def change(request, operation, otp_code):
    user, session, device = actor_and_device(request, 'totp:' + operation)
    limited_request(request, 'totp-management', str(user.pk))
    codes = None
    if operation == 'enable':
        if (device.active_secret or not device.pending_secret or device.pending_expires_at is None
                or device.pending_expires_at <= timezone.now() or device.pending_session_id != session.pk
                or device.pending_session_version != user.session_version
                or not hmac.compare_digest(device.pending_password_digest, password_digest(user))):
            raise ValidationError('设置已失效，请重新设置双因素认证')
        consume_proof(device, otp_code, allow_recovery=False, pending=True)
        device.active_secret = device.pending_secret
        codes = new_recovery_codes(device)
    else:
        if not device.active_secret:
            raise ValidationError('双因素认证未启用')
        consume_proof(device, otp_code)
        if operation == 'disable':
            device.active_secret = ''
            device.last_counter = -1
            device.recovery_hashes = []
        else:
            codes = new_recovery_codes(device)
    clear_pending(device)
    device.save()
    user.session_version += 1
    user.save(update_fields=['session_version', 'updated_at'])
    audit(request, user, 'totp_' + operation)
    from .serializers import UserSerializer
    token = issue_session(user, request)
    result = {'access': str(token.access_token), 'refresh': str(token), 'user': UserSerializer(user).data}
    if codes is not None:
        result['recovery_codes'] = codes
    return result
