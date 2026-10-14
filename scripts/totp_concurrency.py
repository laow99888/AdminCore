"""仅 foundation PostgreSQL/Redis：独立 RFC6238 生成器和双因素竞态验收。"""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import hmac
import json
import secrets
import struct
from threading import Barrier
import time
import uuid

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from django.test import override_settings
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.test import APIClient

from apps.auth_app.models import EmailChallenge, TOTPDevice
from apps.auth_app.sessions import issue_session
from apps.logs.models import OperationLog
from apps.core.models import OutboxEvent

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
assert 'redis' in settings.CACHES['default']['BACKEND'].lower(), '必须使用共享 Redis'
User = get_user_model()
CHECKS, CREATED, SENSITIVE, USERNAMES, IPS = [], [], [], [], []
started_window = int(time.time() // 60)
ip_sequence = 1


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)
    print('通过：TOTP 验收 ' + label, flush=True)


def proof(secret, counter=None):
    """脚本独立 RFC 4226/6238 实现，绝不调用生产认证函数。"""
    counter = int(time.time() // 30) if counter is None else counter
    digest = hmac.new(base64.b32decode(secret), struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0f
    number = int.from_bytes(digest[offset:offset + 4], 'big') & 0x7fffffff
    return f'{number % 1000000:06d}'


def client_for(access=None):
    global ip_sequence
    ip_sequence += 1
    ip = f'127.0.2.{ip_sequence % 250 + 1}'
    IPS.append(ip)
    client = APIClient(HTTP_HOST='backend', REMOTE_ADDR=ip)
    if access:
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(access))
    return client


def post(path, data, access=None):
    return client_for(access).post('/api/v1/auth/' + path + '/', data, format='json')


def fixture():
    password = secrets.token_urlsafe(40)
    actor = User.objects.create_user('totp-' + uuid.uuid4().hex[:12],
        email=uuid.uuid4().hex + '@example.test', password=password)
    CREATED.append(actor.pk)
    USERNAMES.append(actor.username)
    SENSITIVE.append(password)
    return actor, password, issue_session(actor)


def setup(actor, password, token):
    response = post('totp/setup', {'current_password': password}, token.access_token)
    check('密码确认后创建待确认密钥', response.status_code == 200)
    secret = response.json()['data']['secret']
    SENSITIVE.append(secret)
    device = TOTPDevice.objects.get(user=actor)
    check('数据库仅保存Fernet加密密钥', secret not in device.pending_secret
          and Fernet(settings.AUTH_TOTP_ENCRYPTION_KEY.encode()).decrypt(device.pending_secret.encode()).decode() == secret)
    check('设置响应私有无缓存且包含RFC认证器URI', response['Cache-Control'] == 'private, no-store'
          and response.json()['data']['otpauth_uri'].startswith('otpauth://totp/'))
    return secret


def enable(actor, password, token):
    secret = setup(actor, password, token)
    # 特意用上一格启用，以留当前格验证重放；密码哈希核对跨边界会令它老两格。
    # 在时间步前 20 秒提交，避免把正常的窗口拒绝误判为实现故障。
    while time.time() % 30 > 20:
        time.sleep(0.25)
    response = post('totp/enable', {'current_password': password,
        'otp_code': proof(secret, int(time.time() // 30) - 1)}, token.access_token)
    check('动态码确认启用并签发新会话', response.status_code == 200)
    data = response.json()['data']
    codes = data['recovery_codes']
    SENSITIVE.extend(codes)
    check('启用仅一次返回10个不同恢复码', len(codes) == len(set(codes)) == 10)
    check('启用立即撤销原access与refresh', client_for(token.access_token).get('/api/v1/auth/me/').status_code == 401
          and post('refresh', {'refresh': str(token)}).status_code == 400)
    check('新会话可获取双因素状态', client_for(data['access']).get('/api/v1/auth/totp/').json()['data'] ==
          {'enabled': True, 'available': True, 'recovery_codes_remaining': 10})
    return secret, data


def login(actor, password, otp=None):
    data = {'username': actor.username, 'password': password}
    if otp is not None:
        data['otp_code'] = otp
    return post('login', data)


def no_tokens(response):
    return 'access' not in response.json() and 'refresh' not in response.json() and 'access' not in (response.json().get('data') or {})


def parallel(callbacks):
    barrier = Barrier(len(callbacks))

    def invoke(callback):
        try:
            barrier.wait(timeout=10)
            return callback()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(callbacks)) as pool:
        futures = [pool.submit(invoke, callback) for callback in callbacks]
        return [future.result(timeout=20) for future in futures]


try:
    # RFC 6238 附录B已知向量（SHA1 8位转6位）。
    vector_secret = base64.b32encode(b'12345678901234567890').decode()
    check('独立RFC6238生成器已知向量', proof(vector_secret, 59 // 30) == '287082')
    actor, password, token = fixture()
    other = issue_session(actor)
    secret, enabled = enable(actor, password, token)
    check('启用同样撤销其它设备', client_for(other.access_token).get('/api/v1/auth/me/').status_code == 401)
    missing = login(actor, password)
    check('仅正确密码不能绕过第二因素', missing.status_code == 401 and no_tokens(missing)
          and 'mfa_required' in json.dumps(missing.json()))
    current = proof(secret)
    now_counter = int(time.time() // 30)
    accepted = {proof(secret, step) for step in range(now_counter - 1, now_counter + 2)}
    wrong = next(f'{value:06d}' for value in range(100) if f'{value:06d}' not in accepted)
    check('错误认证码不签发会话', login(actor, password, wrong).status_code == 401)
    results = parallel([lambda: login(actor, password, current), lambda: login(actor, password, current)])
    check('PostgreSQL 同动态码并发仅一个登录成功', sorted(response.status_code for response in results) == [200, 401])
    check('已消费动态码禁止重放', login(actor, password, current).status_code == 401)
    device = TOTPDevice.objects.get(user=actor)
    check('动态码失败不消耗恢复码', len(device.recovery_hashes) == 10)

    actor, password, token = fixture()
    secret, enabled = enable(actor, password, token)
    code = enabled['recovery_codes'][0]
    results = parallel([lambda: login(actor, password, code), lambda: login(actor, password, code)])
    check('PostgreSQL 同恢复码并发仅一个登录成功', sorted(response.status_code for response in results) == [200, 401])
    check('恢复码消费后禁止重放', login(actor, password, code).status_code == 401)
    check('恢复码只删除成功使用的一条', len(TOTPDevice.objects.get(user=actor).recovery_hashes) == 9)
    regen = post('totp/recovery-codes', {'current_password': password,
        'otp_code': enabled['recovery_codes'][1]}, enabled['access'])
    check('恢复码轮换需要密码及第二因素', regen.status_code == 200)
    rotated = regen.json()['data']
    SENSITIVE.extend(rotated['recovery_codes'])
    check('恢复码轮换签发10条全新代码', len(rotated['recovery_codes']) == 10
          and not set(rotated['recovery_codes']) & set(enabled['recovery_codes']))
    check('轮换立即撤销旧会话', client_for(enabled['access']).get('/api/v1/auth/me/').status_code == 401
          and post('refresh', {'refresh': enabled['refresh']}).status_code == 400)
    check('轮换前未使用恢复码也全部失效', login(actor, password, enabled['recovery_codes'][2]).status_code == 401)
    check('错误密码不能关闭第二因素', post('totp/disable', {'current_password': 'incorrect',
        'otp_code': rotated['recovery_codes'][0]}, rotated['access']).status_code == 403)
    check('缺少第二因素不能关闭', post('totp/disable', {'current_password': password}, rotated['access']).status_code == 400)
    disabled = post('totp/disable', {'current_password': password,
        'otp_code': rotated['recovery_codes'][0]}, rotated['access'])
    check('正确密码及第二因素可以关闭', disabled.status_code == 200)
    disabled_device = TOTPDevice.objects.get(user=actor)
    check('关闭清空密钥与所有恢复码', not disabled_device.active_secret and not disabled_device.recovery_hashes)
    check('关闭后密码登录恢复且旧会话失效', login(actor, password).status_code == 200
          and client_for(rotated['access']).get('/api/v1/auth/me/').status_code == 401)

    for invalidation in ['expired', 'different-session', 'password-changed']:
        actor, password, token = fixture()
        secret = setup(actor, password, token)
        access = token.access_token
        if invalidation == 'expired':
            TOTPDevice.objects.filter(user=actor).update(pending_expires_at=timezone.now() - timedelta(seconds=1))
        elif invalidation == 'different-session':
            access = issue_session(actor).access_token
        else:
            candidate = secrets.token_urlsafe(40)
            response = post('change_password', {'old_password': password, 'new_password': candidate,
                'new_password2': candidate}, token.access_token)
            check('待确认期间修改密码成功', response.status_code == 200)
            password = candidate
            access = login(actor, password).json()['access']
        response = post('totp/enable', {'current_password': password, 'otp_code': proof(secret)}, access)
        check('待确认设置失效：' + invalidation, response.status_code == 400
              and not TOTPDevice.objects.get(user=actor).active_secret)

    actor, password, token = fixture()
    secret, enabled = enable(actor, password, token)
    candidate = secrets.token_urlsafe(40)
    changed = post('change_password', {'old_password': password, 'new_password': candidate,
        'new_password2': candidate}, enabled['access'])
    check('修改密码不关闭已启用双因素', changed.status_code == 200
          and bool(TOTPDevice.objects.get(user=actor).active_secret)
          and login(actor, candidate).status_code == 401)
    successful = login(actor, candidate, enabled['recovery_codes'][0])
    check('改密后仍需正确第二因素登录', successful.status_code == 200)
    actor.refresh_from_db()
    actor.verified_email = actor.email.casefold()
    actor.save(update_fields=['verified_email'])
    with override_settings(AUTH_EMAIL_ENABLED=True, EMAIL_HOST='127.0.0.1', DEFAULT_FROM_EMAIL='fixture@example.test'):
        request = post('recovery/request', {'username': actor.username, 'email': actor.email})
        check('已启用双因素仍可申请邮箱重置', request.status_code == 202)
        challenge = EmailChallenge.objects.get(user=actor, purpose='reset', consumed_at__isnull=True)
        snapshot = '|'.join([challenge.pk.hex, str(challenge.user_id), challenge.purpose, challenge.email,
            str(challenge.session_version), challenge.password_digest, challenge.expires_at.isoformat(), challenge.signing_key_digest])
        recovery_code = challenge.pk.hex + '.' + salted_hmac('admincore.auth.email.v1', snapshot,
            secret=settings.SECRET_KEY, algorithm='sha256').hexdigest()
        new_password = secrets.token_urlsafe(40)
        reset = post('recovery/reset', {'code': recovery_code, 'new_password': new_password,
                                      'new_password2': new_password})
        check('邮箱重置后双因素仍启用', reset.status_code == 200
              and bool(TOTPDevice.objects.get(user=actor).active_secret)
              and login(actor, new_password).status_code == 401)
        check('邮箱重置后有效第二因素仍能登录', login(actor, new_password, enabled['recovery_codes'][1]).status_code == 200)

    actor, password, token = fixture()
    secret, enabled = enable(actor, password, token)
    with override_settings(AUTH_TOTP_ENCRYPTION_KEY=''):
        response = login(actor, password, enabled['recovery_codes'][0])
        check('缺加密配置的已启用账户拒绝登录', response.status_code == 503 and no_tokens(response))
    with override_settings(AUTH_TOTP_ENCRYPTION_KEY=Fernet.generate_key().decode()):
        response = login(actor, password, proof(secret))
        check('错误加密密钥的已启用账户拒绝登录', response.status_code == 503 and no_tokens(response))

    from django.test import Client
    admin, admin_password, _ = fixture()
    admin.is_staff = True
    admin.is_superuser = True
    admin.save(update_fields=['is_staff', 'is_superuser'])
    secret, enabled_admin = enable(admin, admin_password, issue_session(admin))
    session_client = Client(HTTP_HOST='backend')
    response = session_client.post('/admin/login/?next=/admin/',
        {'username': admin.username, 'password': admin_password, 'next': '/admin/'})
    check('Django admin密码入口不能绕过双因素', response.status_code == 200
          and '_auth_user_id' not in session_client.session)
    values = json.dumps({'factors': list(TOTPDevice.objects.filter(user_id__in=CREATED).values()),
        'audit': list(OperationLog.objects.filter(user_id__in=CREATED).values()),
        'events': list(OutboxEvent.objects.filter(topic='auth.email').values())}, default=str)
    check('密钥和原始恢复码不落库或审计正文', all(value not in values for value in SENSITIVE))
finally:
    # 只清理本脚本登记的随机夹具；正常服务与其它验收数据均不触碰。
    challenge_ids = list(EmailChallenge.objects.filter(user_id__in=CREATED).values_list('id', flat=True))
    OutboxEvent.objects.filter(topic='auth.email', payload__challenge_id__in=[str(pk) for pk in challenge_ids]).delete()
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    OutstandingToken.objects.filter(user_id__in=CREATED).delete()
    User.objects.filter(pk__in=CREATED).delete()
    keys = []
    for window in range(started_window, int(time.time() // 60) + 1):
        for ip in set(IPS):
            digest = hashlib.sha256(ip.encode()).hexdigest()
            keys.append(f'login:ip:{digest}:{window}')
            for purpose in ['totp-login', 'totp-management', 'totp-setup', 'reset-request']:
                keys.append(f'auth-email:{purpose}:ip:{digest}:{window}')
        for identifier in CREATED:
            identity = str(identifier)
            digest = hashlib.sha256(identity.encode()).hexdigest()
            for purpose in ['totp-login', 'totp-management', 'totp-setup']:
                keys.append(f'auth-email:{purpose}:identity:{digest}:{window}')
            keys.append('password-confirmation:' + hashlib.sha256(f'user:{identifier}'.encode()).hexdigest() + f':{window}')
            for scope in ['totp:setup', 'totp:enable', 'totp:disable', 'totp:recovery-codes']:
                keys.append('password-confirmation:' + hashlib.sha256(f'scope:{identifier}:{scope}'.encode()).hexdigest() + f':{window}')
        for username in USERNAMES:
            digest = hashlib.sha256(username.casefold().encode()).hexdigest()
            keys.extend([f'login:username:{digest}:{window}', f'auth-email:reset-request:identity:{digest}:{window}'])
    cache.delete_many(keys)
    assert not User.objects.filter(pk__in=CREATED).exists(), '随机账号夹具清理不完整'
    assert not TOTPDevice.objects.filter(user_id__in=CREATED).exists(), '双因素夹具清理不完整'
    connections.close_all()
print('TOTP PostgreSQL/Redis 验收通过：' + str(len(CHECKS)) + ' 项；随机夹具已清理，无常驻进程')
