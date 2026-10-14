"""foundation 专用 SQL 验证码验收；可在 minimal/standard 容器 shell 执行。

答案只在测试渲染边界捕获，不从数据库反推、不增加产品接口；真实图片生成、
SQL/密码/JWT/第二因素校验均执行。子进程凭据只经 stdin，输出仅状态码。
"""
import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
import hashlib
import hmac
import io
import json
import secrets
import struct
import subprocess
import sys
from threading import Barrier, Event
import time
from unittest.mock import patch
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections, OperationalError
from django.db.models.query import QuerySet
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.auth_app import login_captcha
from apps.auth_app.models import AuthSession, LoginCaptchaGuard, LoginCaptchaChallenge
from apps.auth_app.sessions import issue_session
from apps.core.tasks import cleanup_expired_sessions
from apps.logs.models import LoginLog, OperationLog

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
User = get_user_model()
CHECKS, CREATED, GUARDS, CHALLENGES, PAIRS = [], [], set(), set(), set()
ip_index = 0
started_window = int(time.time() // 60)


def check(label, value):
    if not value:
        raise AssertionError(label)
    CHECKS.append(label)
    print('通过：验证码验收 ' + label, flush=True)


def register(username, ip):
    PAIRS.add((username, ip))
    pair, ip_digest = login_captcha.identities(Request(APIRequestFactory().post('/', {}, REMOTE_ADDR=ip)), username)
    GUARDS.update([pair, ip_digest])
    return pair, ip_digest


def client(ip):
    return APIClient(HTTP_HOST='backend', REMOTE_ADDR=ip)


def fixture():
    global ip_index
    ip_index += 1
    ip = f'127.0.3.{ip_index}'
    password = secrets.token_urlsafe(40)
    actor = User.objects.create_user('captcha-' + uuid.uuid4().hex[:12], password=password)
    CREATED.append(actor.pk)
    register(actor.username, ip)
    return actor, password, ip


def clear_fixture_login_limit(username, ip):
    # 验证码专项分段验证时只重置本夹具的既有限流计数，不flush共享缓存。
    window = int(time.time() // 60)
    cache.delete_many([f'login:username:{hashlib.sha256(username.casefold().encode()).hexdigest()}:{window}',
                       f'login:ip:{hashlib.sha256(ip.encode()).hexdigest()}:{window}'])


def login(username, password, ip, challenge=None, answer=None, otp=None):
    register(username, ip)
    data = {'username': username, 'password': password}
    if challenge is not None:
        data.update(captcha_id=challenge, captcha_code=answer)
    if otp is not None:
        data['otp_code'] = otp
    return client(ip).post('/api/v1/auth/login/', data, format='json')


def seed_gate(username, ip, count=3, ip_count=0):
    pair, ip_digest = register(username, ip)
    for identity, failures in [(pair, count), (ip_digest, ip_count)]:
        LoginCaptchaGuard.objects.update_or_create(identity_digest=identity, defaults={
            'failure_count': failures, 'failure_expires_at': timezone.now() + timedelta(minutes=15),
            'expires_at': timezone.now() + timedelta(minutes=15), 'refresh_window': -1,
            'refresh_count': 0, 'current_challenge_id': None})


def challenge(username, ip):
    register(username, ip)
    answers = []
    real_render = login_captcha.render_captcha

    def capture(answer):
        answers.append(answer)
        return real_render(answer)

    with patch.object(login_captcha, 'render_captcha', side_effect=capture):
        response = client(ip).post('/api/v1/auth/login-captcha/', {'username': username}, format='json')
    check('挑战返回私有无缓存PNG', response.status_code == 200
          and response['Cache-Control'] == 'private, no-store')
    data = response.json()['data']
    check('验证码响应仅图片及挑战元数据', set(data) == {'required', 'challenge_id', 'image', 'expires_in'}
          and data['required'] and data['expires_in'] == 120 and len(answers) == 1)
    with Image.open(io.BytesIO(base64.b64decode(data['image'].split(',', 1)[1]))) as image:
        check('PNG图片内容可以真实解码', image.format == 'PNG' and image.size == (180, 64))
    CHALLENGES.add(data['challenge_id'])
    return data['challenge_id'], answers[0]


def error_code(response, expected):
    return response.status_code == 400 and response.json().get('data', {}).get('code') == expected


CHILD = '''import json,sys,os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from django.test import override_settings
from django.db import connections
from rest_framework.test import APIClient
data=json.load(sys.stdin)
try:
 with override_settings(AUTH_LOGIN_CAPTCHA_ENABLED=True,AUTH_LOGIN_CAPTCHA_FAILURE_THRESHOLD=3):
  c=APIClient(HTTP_HOST='backend',REMOTE_ADDR=data['ip'])
  r=c.post(data['path'],data['payload'],format='json')
  print(json.dumps({'status':r.status_code,'required':(r.json().get('data') or {}).get('required')}))
finally:
 connections.close_all()
'''


def child(ip, path, payload):
    result = subprocess.run([sys.executable, '-c', CHILD], input=json.dumps({'ip': ip,
        'path': '/api/v1/auth/' + path + '/', 'payload': payload}), capture_output=True,
        text=True, timeout=25)
    if result.returncode:
        raise AssertionError('验证码隔离子进程失败（凭据不写日志）')
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise AssertionError('验证码隔离子进程未返回受控状态') from None


def parallel(callbacks):
    barrier = Barrier(len(callbacks))

    def invoke(callback):
        try:
            barrier.wait(timeout=10)
            return callback()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=len(callbacks)) as pool:
        futures = [pool.submit(invoke, fn) for fn in callbacks]
        return [future.result(timeout=35) for future in futures]


def totp(secret):
    digest = hmac.new(base64.b32decode(secret), struct.pack('>Q', int(time.time() // 30)), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f'{(int.from_bytes(digest[offset:offset + 4], "big") & 0x7fffffff) % 1000000:06d}'


def cleanup_race(mode):
    actor, _, ip = fixture()
    pair_key, ip_key = register(actor.username, ip)
    target_key = ip_key if mode == 'issue-ip' else pair_key
    LoginCaptchaGuard.objects.create(identity_digest=target_key,
        expires_at=timezone.now() - timedelta(days=2))
    fetched, release, cleaning = Event(), Event(), Event()
    real_get = QuerySet.get_or_create
    request = Request(APIRequestFactory().post('/', {}, REMOTE_ADDR=ip))

    def pause_after_get(queryset, *args, **kwargs):
        result = real_get(queryset, *args, **kwargs)
        if queryset.model is LoginCaptchaGuard and kwargs.get('identity_digest') == target_key and not fetched.is_set():
            fetched.set()
            if not release.wait(10):
                raise AssertionError('guard竞争测试未释放获取线程')
        return result

    def reuse():
        try:
            if mode == 'issue-ip':
                return login_captcha.issue_challenge(request, actor.username)
            return login_captcha.record_failure(request, actor.username)
        finally:
            connections.close_all()

    def clean():
        try:
            cleaning.set()
            return cleanup_expired_sessions()
        finally:
            connections.close_all()

    with patch.object(QuerySet, 'get_or_create', new=pause_after_get):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(reuse)
            check('旧guard首次读取进入事务：' + mode, fetched.wait(10))
            second = pool.submit(clean)
            check('过期清理线程开始执行：' + mode, cleaning.wait(10))
            try:
                try:
                    second.result(timeout=0.25)
                    raise AssertionError('旧guard获取后清理未等待行锁：' + mode)
                except TimeoutError:
                    check('首次获取已锁定旧guard阻止中途删除：' + mode, True)
            finally:
                release.set()
            first.result(timeout=10)
            second.result(timeout=10)
    guard = LoginCaptchaGuard.objects.filter(pk=target_key).first()
    check('复用延期后清理重检保留guard：' + mode, guard is not None and guard.expires_at > timezone.now())


try:
    with override_settings(AUTH_LOGIN_CAPTCHA_ENABLED=True, AUTH_LOGIN_CAPTCHA_FAILURE_THRESHOLD=3):
        cleanup_race('issue-ip')
        cleanup_race('failure-pair')
        actor, password, ip = fixture()
        initial = client(ip).post('/api/v1/auth/login-captcha/', {'username': actor.username}, format='json')
        check('未失败账户不要求图形验证码', initial.status_code == 200 and initial.json()['data'] == {'required': False})
        check('匿名挑战拒绝额外字段', client(ip).post('/api/v1/auth/login-captcha/',
            {'username': actor.username, 'answer': 'unsupported'}, format='json').status_code == 400)
        check('匿名挑战拒绝GET方法且不缓存', client(ip).get('/api/v1/auth/login-captcha/').status_code == 405)
        for attempt in range(3):
            failure = login(actor.username, 'incorrect', ip)
            check('真实错误密码累加失败', failure.status_code == 401)
            if attempt == 2:
                check('第N次失败立即提示获取验证码', failure.json().get('data', {}).get('code') == 'captcha_required')
        pair, ip_digest = register(actor.username, ip)
        check('SQL记录达到三次失败阈值', LoginCaptchaGuard.objects.get(pk=pair).failure_count == 3)
        clear_fixture_login_limit(actor.username, ip)
        check('缺验证码不会继续验证密码', error_code(login(actor.username, password, ip), 'captcha_required'))
        identifier, answer = challenge(actor.username, ip)
        wrong = '22222' if answer != '22222' else '33333'
        check('错误验证码返回统一拒绝', error_code(login(actor.username, password, ip, identifier, wrong), 'captcha_invalid'))
        check('错误尝试同样消费挑战', LoginCaptchaChallenge.objects.get(pk=identifier).consumed_at is not None)
        check('消费后正确答案仍不可重放', error_code(login(actor.username, password, ip, identifier, answer), 'captcha_invalid'))

        actor, password, ip = fixture()
        seed_gate(actor.username, ip)
        identifier, answer = challenge(actor.username, ip)
        check('正确验证码配错误密码仍拒绝登录', login(actor.username, 'incorrect', ip, identifier, answer).status_code == 401)
        check('密码失败回滚不复活已消费验证码', LoginCaptchaChallenge.objects.get(pk=identifier).consumed_at is not None
              and error_code(login(actor.username, password, ip, identifier, answer), 'captcha_invalid'))

        actor, password, ip = fixture()
        seed_gate(actor.username, ip)
        old_id, old_answer = challenge(actor.username, ip)
        identifier, answer = challenge(actor.username, ip)
        check('刷新图片废止原挑战', error_code(login(actor.username, password, ip, old_id, old_answer), 'captcha_invalid'))
        LoginCaptchaChallenge.objects.filter(pk=identifier).update(expires_at=timezone.now() - timedelta(seconds=1))
        check('过期挑战拒绝密码登录', error_code(login(actor.username, password, ip, identifier, answer), 'captcha_invalid'))

        actor, password, ip = fixture()
        seed_gate(actor.username, ip)
        identifier, answer = challenge(actor.username, ip)
        victim = actor.username
        foreign = 'unknown-' + uuid.uuid4().hex
        foreign_ip = '127.0.4.1'
        seed_gate(foreign, ip)
        seed_gate(victim, foreign_ip)
        check('挑战不能跨用户名使用', error_code(login(foreign, password, ip, identifier, answer), 'captcha_invalid'))
        check('挑战不能跨IP使用', error_code(login(victim, password, foreign_ip, identifier, answer), 'captcha_invalid'))
        check('跨绑定恶意尝试不消费受害者挑战', LoginCaptchaChallenge.objects.get(pk=identifier).consumed_at is None)
        check('绑定正确的持有者仍能成功', login(victim, password, ip, identifier, answer).status_code == 200)

        actor, password, ip = fixture()
        seed_gate(actor.username, ip, ip_count=2)
        identifier, answer = challenge(actor.username, ip)
        payload = {'username': actor.username, 'password': password, 'captcha_id': identifier, 'captcha_code': answer}
        results = parallel([lambda: child(ip, 'login', payload), lambda: child(ip, 'login', payload)])
        check('PostgreSQL跨进程同挑战登录恰有一次成功', sorted(item['status'] for item in results) == [200, 400])
        pair, ip_digest = register(actor.username, ip)
        check('成功清零本组合失败但保留IP聚合失败', LoginCaptchaGuard.objects.get(pk=pair).failure_count == 0
              and LoginCaptchaGuard.objects.get(pk=ip_digest).failure_count == 2)
        check('成功清零后提交旧挑战仍拒绝重放', error_code(login(actor.username, password, ip, identifier, answer), 'captcha_invalid'))

        actor, password, ip = fixture()
        for _ in range(3):
            check('独立进程错误密码仍持久计数', child(ip, 'login', {'username': actor.username, 'password': 'incorrect'})['status'] == 401)
        required = child(ip, 'login-captcha', {'username': actor.username})
        check('跨进程读取共享SQL门槛', required['status'] == 200 and required['required'] is True)
        # 不存在用户名与已有账户同失败次数，不应按是否存在决定挑战。
        unknown = 'unknown-' + uuid.uuid4().hex
        seed_gate(unknown, ip)
        response = client(ip).post('/api/v1/auth/login-captcha/', {'username': unknown}, format='json')
        check('不存在账户挑战结构与已有账户一致', response.status_code == 200
              and set(response.json()['data']) == {'required', 'challenge_id', 'image', 'expires_in'}
              and response.json()['data']['required'])
        CHALLENGES.add(response.json()['data']['challenge_id'])

        actor, password, ip = fixture()
        seed_gate(actor.username, ip, count=0, ip_count=10)
        check('IP聚合门槛保护尚未失败组合', error_code(login(actor.username, password, ip), 'captcha_required'))
        seed_gate(actor.username, ip, count=3, ip_count=0)
        pair, ip_digest = register(actor.username, ip)
        LoginCaptchaGuard.objects.filter(pk__in=[pair, ip_digest]).update(failure_expires_at=timezone.now() - timedelta(seconds=1))
        response = client(ip).post('/api/v1/auth/login-captcha/', {'username': actor.username}, format='json')
        check('固定15分钟窗口过期解除门槛', response.status_code == 200 and response.json()['data'] == {'required': False})

        actor, password, ip = fixture()
        seed_gate(actor.username, ip)
        frozen = timezone.now()
        with patch('apps.auth_app.login_captcha.timezone.now', return_value=frozen):
            for _ in range(10):
                response = client(ip).post('/api/v1/auth/login-captcha/', {'username': actor.username}, format='json')
                check('挑战限频范围内可以刷新', response.status_code == 200)
                CHALLENGES.add(response.json()['data']['challenge_id'])
            response = client(ip).post('/api/v1/auth/login-captcha/', {'username': actor.username}, format='json')
        check('第11次刷新被SQL共享限频拒绝', response.status_code == 429)
        actor, password, ip = fixture()
        with patch.object(LoginCaptchaGuard.objects, 'select_for_update', side_effect=OperationalError('fixture-private-sql-detail')):
            response = login(actor.username, password, ip)
            check('SQL不可用登录拒绝且无token', response.status_code == 503 and 'access' not in response.json())
            check('SQL故障详情不泄漏到响应', 'fixture-private-sql-detail' not in json.dumps(response.json()))
        real_lock = login_captcha.locked_guards
        calls = []

        def fail_success(*args):
            calls.append(True)
            if len(calls) > 1:
                raise OperationalError('fixture-private-post-password')
            return real_lock(*args)

        with patch.object(login_captcha, 'locked_guards', side_effect=fail_success):
            response = login(actor.username, password, ip)
            check('密码成功但SQL清零故障仍关闭登录', response.status_code == 503
                  and not AuthSession.objects.filter(user=actor).exists()
                  and not LoginLog.objects.filter(user=actor, status='success').exists())

        actor, password, ip = fixture()
        token = issue_session(actor)
        authenticated = client(ip)
        authenticated.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
        setup = authenticated.post('/api/v1/auth/totp/setup/', {'current_password': password}, format='json')
        check('验证码可与TOTP设置共用认证架构', setup.status_code == 200)
        secret = setup.json()['data']['secret']
        enabled = authenticated.post('/api/v1/auth/totp/enable/', {'current_password': password, 'otp_code': totp(secret)}, format='json')
        check('TOTP串联夹具启用成功', enabled.status_code == 200)
        recovery_code = enabled.json()['data']['recovery_codes'][0]
        seed_gate(actor.username, ip)
        identifier, answer = challenge(actor.username, ip)
        response = login(actor.username, password, ip, identifier, answer)
        check('验证码正确但缺第二因素仍不给token', response.status_code == 401
              and 'mfa_required' in json.dumps(response.json()) and 'access' not in response.json())
        pair, _ = register(actor.username, ip)
        check('mfa_required不增加失败且已消费验证码', LoginCaptchaGuard.objects.get(pk=pair).failure_count == 3
              and LoginCaptchaChallenge.objects.get(pk=identifier).consumed_at is not None)
        identifier, answer = challenge(actor.username, ip)
        check('重新取验证码后第二因素串联成功', login(actor.username, password, ip, identifier, answer, recovery_code).status_code == 200)

        actor, password, ip = fixture()
        seed_gate(actor.username, ip)
        with override_settings(AUTH_LOGIN_CAPTCHA_ENABLED=False):
            response = client(ip).post('/api/v1/auth/login-captcha/', {'username': actor.username}, format='json')
            check('关闭配置保留正常密码登录', response.json()['data'] == {'required': False}
                  and login(actor.username, password, ip).status_code == 200)
        actor, password, ip = fixture()
        with override_settings(AUTH_LOGIN_CAPTCHA_ENABLED=False):
            frozen = time.time()
            with patch('apps.auth_app.throttling.time.time', return_value=frozen):
                for _ in range(5):
                    check('原有用户名限流范围内返回认证失败', login(actor.username, 'incorrect', ip).status_code == 401)
                check('关闭验证码仍保留原有登录限流', login(actor.username, 'incorrect', ip).status_code == 429)
finally:
    # 仅脚本记录的随机身份/账号清理；不用flush或按表删除。
    LoginCaptchaChallenge.objects.filter(pair_digest__in=GUARDS).delete()
    LoginCaptchaGuard.objects.filter(pk__in=GUARDS).delete()
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    OutstandingToken.objects.filter(user_id__in=CREATED).delete()
    LoginLog.objects.filter(username__in=[username for username, _ in PAIRS]).delete()
    OperationLog.objects.filter(user_id__in=CREATED).delete()
    User.objects.filter(pk__in=CREATED).delete()
    keys = []
    for window in range(started_window, int(time.time() // 60) + 1):
        for username, ip in PAIRS:
            keys.extend([f'login:username:{hashlib.sha256(username.casefold().encode()).hexdigest()}:{window}',
                         f'login:ip:{hashlib.sha256(ip.encode()).hexdigest()}:{window}'])
        for actor_id in CREATED:
            digest = hashlib.sha256(str(actor_id).encode()).hexdigest()
            keys.extend([f'auth-email:totp-login:identity:{digest}:{window}', f'auth-email:totp-management:identity:{digest}:{window}'])
    cache.delete_many(keys)
    connections.close_all()
print('SQL登录验证码验收通过：' + str(len(CHECKS)) + '项；随机夹具清理，子进程均已退出')
