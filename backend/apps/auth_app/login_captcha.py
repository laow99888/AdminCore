"""登录门槛验证码：SQL 共享计数、一次消费、图片生成不返回明文答案。"""
import base64
import hmac
import io
import secrets
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from PIL import Image, ImageDraw, ImageFont
from rest_framework.exceptions import APIException, Throttled, ValidationError
from rest_framework.throttling import BaseThrottle

from .models import LoginCaptchaChallenge, LoginCaptchaGuard

ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
WINDOW = timedelta(minutes=15)


class CaptchaUnavailable(APIException):
    status_code = 503
    default_detail = '登录验证暂不可用，请稍后重试'
    default_code = 'captcha_unavailable'


def enabled():
    return getattr(settings, 'AUTH_LOGIN_CAPTCHA_ENABLED', False)


def identities(request, username):
    ip = BaseThrottle().get_ident(request)
    normalized = str(username).strip().casefold()
    digest = lambda value: salted_hmac('admincore.auth.login-captcha.identity.v1', value,
                                      secret=settings.SECRET_KEY, algorithm='sha256').hexdigest()
    return digest('pair:' + ip + '\0' + normalized), digest('ip:' + ip)


def answer_digest(identifier, answer):
    return salted_hmac('admincore.auth.login-captcha.v1', f'{identifier}:{answer}',
                      secret=settings.SECRET_KEY, algorithm='sha256').hexdigest()


def locked_guards(pair, ip):
    """所有路径按 identity_digest 排序锁；新行唯一约束保护首次并发。"""
    now = timezone.now()
    guards = {}
    for key in sorted([pair, ip]):
        guard, _ = LoginCaptchaGuard.objects.select_for_update().get_or_create(identity_digest=key,
            defaults={'expires_at': now + WINDOW})
        if guard.failure_expires_at is None or guard.failure_expires_at <= now:
            reset_needed = guard.failure_count != 0 or guard.failure_expires_at is not None
            guard.failure_count = 0
            guard.failure_expires_at = None
            if reset_needed:
                guard.save(update_fields=['failure_count', 'failure_expires_at'])
        guards[key] = guard
    return guards[pair], guards[ip]


def gated(pair, ip):
    return pair.failure_count >= settings.AUTH_LOGIN_CAPTCHA_FAILURE_THRESHOLD or ip.failure_count >= 10


def render_captcha(answer):
    image = Image.new('RGB', (180, 64), '#f4f6fa')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=30)
    for _ in range(12):
        draw.line([(secrets.randbelow(180), secrets.randbelow(64)),
                   (secrets.randbelow(180), secrets.randbelow(64))], fill='#a6b2c4', width=1)
    for index, character in enumerate(answer):
        draw.text((14 + index * 31, 10 + secrets.randbelow(8)), character, font=font, fill='#25324a')
    output = io.BytesIO()
    image.save(output, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()


def issue_challenge(request, username):
    if not enabled():
        return {'required': False}
    try:
        # 先独立领取 IP 配额，超额用户名不创建新 pair 行；释放锁后才排序锁 pair+IP。
        pair_key, ip_key = identities(request, username)
        with transaction.atomic():
            now = timezone.now()
            window = int(now.timestamp() // 60)
            ip, _ = LoginCaptchaGuard.objects.select_for_update().get_or_create(identity_digest=ip_key,
                defaults={'expires_at': now + WINDOW})
            if ip.refresh_window != window:
                ip.refresh_window, ip.refresh_count = window, 0
            ip.refresh_count = min(ip.refresh_count + 1, 1000000)
            ip.expires_at = max(ip.expires_at, now + WINDOW)
            ip.save(update_fields=['refresh_window', 'refresh_count', 'expires_at'])
            ip_limited = ip.refresh_count > 10
        if ip_limited:
            raise Throttled(wait=60 - now.timestamp() % 60)
        with transaction.atomic():
            pair, ip = locked_guards(pair_key, ip_key)
            now = timezone.now()
            window = int(now.timestamp() // 60)
            if pair.refresh_window != window:
                pair.refresh_window, pair.refresh_count = window, 0
            pair.refresh_count += 1
            pair.expires_at = max(pair.expires_at, now + WINDOW)
            pair.save()
            limited = pair.refresh_count > 10
            data = {'required': gated(pair, ip)}
            if not limited and data['required']:
                if pair.current_challenge_id:
                    LoginCaptchaChallenge.objects.filter(pk=pair.current_challenge_id, consumed_at__isnull=True).update(consumed_at=now)
                answer = ''.join(secrets.choice(ALPHABET) for _ in range(5))
                try:
                    rendered = render_captcha(answer)
                except Exception:
                    raise CaptchaUnavailable() from None
                challenge = LoginCaptchaChallenge(pair_digest=pair.pk, expires_at=now + timedelta(seconds=120))
                challenge.answer_digest = answer_digest(challenge.pk, answer)
                challenge.save()
                pair.current_challenge_id = challenge.pk
                pair.save(update_fields=['current_challenge_id'])
                data.update(challenge_id=str(challenge.pk), image=rendered, expires_in=120)
        # 限频计数必须提交，不因 429 回滚。
        if limited:
            raise Throttled(wait=60 - now.timestamp() % 60)
        return data
    except DatabaseError:
        raise CaptchaUnavailable() from None


def require_captcha(request, username, identifier=None, code=None):
    if not enabled():
        return
    error = None
    try:
        with transaction.atomic():
            pair, ip = locked_guards(*identities(request, username))
            if not gated(pair, ip) and identifier is None and code is None:
                return
            if identifier is None or code is None:
                error = 'captcha_required'
            else:
                try:
                    parsed = UUID(str(identifier))
                except (ValueError, TypeError):
                    parsed = None
                challenge = LoginCaptchaChallenge.objects.select_for_update().filter(pk=parsed).first() if parsed else None
                now = timezone.now()
                valid_binding = challenge and challenge.pair_digest == pair.pk and pair.current_challenge_id == challenge.pk
                valid = (valid_binding and challenge.consumed_at is None and challenge.expires_at > now
                         and isinstance(code, str) and len(code) == 5
                         and hmac.compare_digest(challenge.answer_digest, answer_digest(challenge.pk, code.upper())))
                # 仅正确绑定能消费，跨 IP/用户名尝试不可使受害者挑战失效。
                if valid_binding and challenge.consumed_at is None:
                    challenge.consumed_at = now
                    challenge.save(update_fields=['consumed_at'])
                if not valid:
                    error = 'captcha_invalid'
        if error:
            raise ValidationError({'detail': '请完成图形验证码验证', 'code': error})
    except DatabaseError:
        raise CaptchaUnavailable() from None


def record_failure(request, username):
    if not enabled():
        return False
    try:
        with transaction.atomic():
            pair, ip = locked_guards(*identities(request, username))
            now = timezone.now()
            for guard in (pair, ip):
                if guard.failure_expires_at is None:
                    guard.failure_expires_at = now + WINDOW
                guard.failure_count = min(guard.failure_count + 1, 1000000)
                guard.expires_at = max(guard.expires_at, guard.failure_expires_at)
                guard.save()
            return gated(pair, ip)
    except DatabaseError:
        raise CaptchaUnavailable() from None


def record_success(request, username):
    if not enabled():
        return
    try:
        with transaction.atomic():
            pair, _ = locked_guards(*identities(request, username))
            pair.failure_count = 0
            pair.failure_expires_at = None
            pair.save(update_fields=['failure_count', 'failure_expires_at'])
    except DatabaseError:
        raise CaptchaUnavailable() from None
