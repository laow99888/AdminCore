"""隔离 foundation PostgreSQL/Redis 的邮箱找回验收；SMTP 仅监听容器 loopback。

由 validate_foundation.py 通过 backend manage.py shell 执行。打印检查名称，
绝不打印密码、邮件正文或确认码；线程和随机 SMTP 端口在 finally 中关闭。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email import policy
from email.parser import BytesParser
import json
import queue
import re
import secrets
import socketserver
from threading import Barrier, Thread
import time
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.models import EmailChallenge
from apps.auth_app.sessions import issue_session
from apps.core.models import OutboxEvent
from apps.core.tasks import dispatch_outbox
from apps.logs.models import OperationLog

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
assert 'redis' in settings.CACHES['default']['BACKEND'].lower(), '必须使用共享 Redis'
User = get_user_model()
CHECKS, CODES, CREATED = [], [], []
ip_sequence = 1


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)
    print('通过：邮箱验收 ' + label, flush=True)


class MailSink(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self):
        self.messages = queue.Queue()
        self.reject = False
        self.reject_delay = 0
        super().__init__(('127.0.0.1', 0), SMTPHandler)


class SMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        self.wfile.write(b'220 localhost isolated fixture\r\n')
        while line := self.rfile.readline(65537):
            verb = line.split(b' ', 1)[0].strip().upper()
            if verb in (b'EHLO', b'HELO'):
                self.wfile.write(b'250 localhost\r\n')
            elif verb in (b'MAIL', b'RCPT', b'RSET', b'NOOP'):
                self.wfile.write(b'250 OK\r\n')
            elif verb == b'DATA':
                if self.server.reject:
                    # 故意提供敏感详情，验证应用仅记录异常类型。
                    if self.server.reject_delay:
                        time.sleep(self.server.reject_delay)
                    self.wfile.write(b'451 fixture-private-smtp-detail\r\n')
                    continue
                self.wfile.write(b'354 send data\r\n')
                chunks = []
                while (part := self.rfile.readline(65537)) not in (b'.\r\n', b''):
                    chunks.append(part[1:] if part.startswith(b'..') else part)
                self.server.messages.put(b''.join(chunks))
                self.wfile.write(b'250 accepted\r\n')
            elif verb == b'QUIT':
                self.wfile.write(b'221 closing\r\n')
                return
            else:
                self.wfile.write(b'502 unsupported\r\n')


def fixture(email=None):
    password = secrets.token_urlsafe(40)
    actor = User.objects.create_user('recovery-' + uuid.uuid4().hex[:12],
        email=email or uuid.uuid4().hex + '@example.test', password=password)
    CREATED.append(actor.pk)
    return actor, password, issue_session(actor)


def client_for(token=None):
    global ip_sequence
    ip_sequence += 1
    client = APIClient(HTTP_HOST='backend', REMOTE_ADDR=f'127.0.1.{ip_sequence % 250 + 1}')
    if token:
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token))
    return client


def post(path, payload, token=None):
    return client_for(token).post('/api/v1/auth/' + path + '/', payload, format='json')


def received_code(sink):
    dispatch_outbox()
    try:
        raw = sink.messages.get(timeout=5)
    except queue.Empty:
        raise AssertionError('本地 SMTP 未收到邮件') from None
    message = BytesParser(policy=policy.default).parsebytes(raw)
    text = message.get_body(preferencelist=('plain',)).get_content()
    matches = re.findall(r'(?<![0-9a-f])[0-9a-f]{32}\.[0-9a-f]{64}(?![0-9a-f])', text)
    check('SMTP 正文包含一个手动确认码', len(matches) == 1)
    CODES.append(matches[0])
    return matches[0]


def verify(actor, password, token, sink):
    response = post('email-verification/request', {'current_password': password}, token.access_token)
    check('验证申请异步受理', response.status_code == 202)
    check('申请响应不包含确认凭据', response.json().get('data') is None)
    code = received_code(sink)
    response = post('email-verification/confirm', {'code': code}, token.access_token)
    check('SMTP 确认码完成邮箱归属验证', response.status_code == 200)
    actor.refresh_from_db()
    check('邮箱归属与当前邮箱一致', actor.email_verified and actor.verified_email == actor.email.casefold())
    return code


def reset_code(actor, sink):
    response = post('recovery/request', {'username': actor.username, 'email': actor.email})
    check('找回申请异步受理', response.status_code == 202)
    return received_code(sink)


def reset(code, candidate):
    return post('recovery/reset', {'code': code, 'new_password': candidate,
                                  'new_password2': candidate})


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


sink = MailSink()
thread = Thread(target=sink.serve_forever, name='isolated-smtp', daemon=True)
thread.start()
try:
    with override_settings(AUTH_EMAIL_ENABLED=True,
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='127.0.0.1',
        EMAIL_PORT=sink.server_address[1], EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='',
        EMAIL_USE_TLS=False, EMAIL_USE_SSL=False, EMAIL_TIMEOUT=3,
        DEFAULT_FROM_EMAIL='admincore-fixture@example.test'):
        actor, password, token = fixture()
        verify(actor, password, token, sink)
        code = reset_code(actor, sink)
        candidate = secrets.token_urlsafe(40)
        check('密码找回成功', reset(code, candidate).status_code == 200)
        check('重置后旧 access 失效', client_for(token.access_token).get('/api/v1/auth/me/').status_code == 401)
        check('重置后旧 refresh 失效', post('refresh', {'refresh': str(token)}).status_code == 400)
        check('重置后新密码可登录', post('login', {'username': actor.username, 'password': candidate}).status_code == 200)
        check('确认凭据不可重复消费', reset(code, secrets.token_urlsafe(40)).status_code == 400)

        before = EmailChallenge.objects.count(), OutboxEvent.objects.filter(topic='auth.email').count()
        known = post('recovery/request', {'username': actor.username, 'email': actor.email})
        # 先消费已验证账户消息，避免影响后续 sink 队列。
        received_code(sink)
        before = EmailChallenge.objects.count(), OutboxEvent.objects.filter(topic='auth.email').count()
        unknown = post('recovery/request', {'username': uuid.uuid4().hex, 'email': uuid.uuid4().hex + '@example.test'})
        check('不存在账户与匹配账户申请响应相同', unknown.status_code == known.status_code == 202
              and unknown.json() == known.json())
        check('不存在账户不登记挑战和邮件事件', before == (
            EmailChallenge.objects.count(), OutboxEvent.objects.filter(topic='auth.email').count()))

        actor, password, token = fixture()
        verify(actor, password, token, sink)
        code = reset_code(actor, sink)
        candidates = [secrets.token_urlsafe(40), secrets.token_urlsafe(40)]
        results = parallel([lambda value=value: reset(code, value) for value in candidates])
        check('PostgreSQL 同确认码并发只有一次重置成功', sorted(item.status_code for item in results) == [200, 400])
        actor.refresh_from_db()
        check('最终密码仅与成功请求一致', actor.check_password(candidates[next(i for i, item in enumerate(results) if item.status_code == 200)]))

        actor, password, token = fixture()
        verify(actor, password, token, sink)
        code = reset_code(actor, sink)
        results = parallel([lambda: reset(code, secrets.token_urlsafe(40)),
                            lambda: post('refresh', {'refresh': str(token)})])
        check('重置与刷新竞争均返回受控响应', results[0].status_code == 200 and results[1].status_code in (200, 400))
        if results[1].status_code == 200:
            rotated = results[1].json()['data']
            check('竞争先签发的 access 不能恢复登录', client_for(rotated['access']).get('/api/v1/auth/me/').status_code == 401)
            check('竞争先签发的 refresh 不能恢复登录', post('refresh', {'refresh': rotated['refresh']}).status_code == 400)
        check('竞争后旧会话仍失效', client_for(token.access_token).get('/api/v1/auth/me/').status_code == 401)

        actor, password, token = fixture()
        check('邮箱竞争验证申请受理', post('email-verification/request', {'current_password': password}, token.access_token).status_code == 202)
        code = received_code(sink)
        new_email = uuid.uuid4().hex + '@example.test'
        results = parallel([lambda: post('email-verification/confirm', {'code': code}, token.access_token),
            lambda: client_for(token.access_token).patch('/api/v1/auth/profile/',
                {'email': new_email, 'profile_version': 1}, format='json')])
        check('邮箱编辑与验证竞争不产生500', all(item.status_code in (200, 400, 409) for item in results))
        actor.refresh_from_db()
        check('邮箱编辑竞争不会绑定旧邮箱到新邮箱',
              (actor.email == new_email and not actor.email_verified and not actor.verified_email)
              or (actor.email != new_email and actor.email_verified and actor.verified_email == actor.email.casefold()))
        if actor.email != new_email:
            response = client_for(token.access_token).patch('/api/v1/auth/profile/',
                {'email': new_email, 'profile_version': actor.profile_version}, format='json')
            actor.refresh_from_db()
            check('验证后修改邮箱必清除归属', response.status_code == 200 and not actor.email_verified and not actor.verified_email)

        shared_email = uuid.uuid4().hex + '@example.test'
        twins = [fixture(shared_email), fixture(shared_email)]
        pair_codes = []
        for actor, password, token in twins:
            check('同未验证邮箱允许分别申请验证', post('email-verification/request',
                {'current_password': password}, token.access_token).status_code == 202)
            pair_codes.append(received_code(sink))
        results = parallel([lambda i=i: post('email-verification/confirm', {'code': pair_codes[i]},
                            twins[i][2].access_token) for i in range(2)])
        check('PostgreSQL 同邮箱归属并发仅允许一个账户', sorted(item.status_code for item in results) == [200, 400]
              and User.objects.filter(verified_email=shared_email).count() == 1)

        actor, password, token = fixture()
        sink.reject = True
        response = post('email-verification/request', {'current_password': password}, token.access_token)
        check('SMTP 故障不改变异步申请响应', response.status_code == 202)
        challenge = EmailChallenge.objects.get(user=actor)
        event = OutboxEvent.objects.get(topic='auth.email', payload__challenge_id=str(challenge.pk))
        dispatch_outbox()
        event.refresh_from_db()
        check('SMTP 故障记录可重试状态且隐藏服务详情', event.status == 'failed' and event.attempts == 1
              and event.available_at > timezone.now() and 'fixture-private' not in event.last_error)
        sink.reject = False
        OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now() - timedelta(seconds=1))
        code = received_code(sink)
        event.refresh_from_db()
        check('SMTP 恢复后可靠事件重试成功', event.status == 'succeeded' and event.attempts == 2 and event.last_error == '')
        check('重试邮件确认码可以消费', post('email-verification/confirm', {'code': code}, token.access_token).status_code == 200)

        actor, password, token = fixture()
        check('并发派发验证申请受理', post('email-verification/request',
            {'current_password': password}, token.access_token).status_code == 202)
        outcomes = parallel([lambda: dispatch_outbox(), lambda: dispatch_outbox()])
        check('PostgreSQL 并发派发只发送一次邮件', sum(result['processed'] for result in outcomes) == 1
              and sink.messages.qsize() == 1)
        code = received_code(sink)
        check('并发派发后的确认码可验证', post('email-verification/confirm',
            {'code': code}, token.access_token).status_code == 200)

        actor, password, token = fixture()
        check('过期测试申请受理', post('email-verification/request',
            {'current_password': password}, token.access_token).status_code == 202)
        challenge = EmailChallenge.objects.get(user=actor)
        EmailChallenge.objects.filter(pk=challenge.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        dispatch_outbox()
        event = OutboxEvent.objects.get(topic='auth.email', payload__challenge_id=str(challenge.pk))
        check('过期待发挑战终止事件且不发邮件', event.status == 'succeeded' and sink.messages.empty())

        actor, password, token = fixture()
        check('替代挑战首个申请受理', post('email-verification/request',
            {'current_password': password}, token.access_token).status_code == 202)
        previous = received_code(sink)
        check('替代挑战第二个申请受理', post('email-verification/request',
            {'current_password': password}, token.access_token).status_code == 202)
        replacement = received_code(sink)
        check('新申请作废旧确认码', previous != replacement and post('email-verification/confirm',
            {'code': previous}, token.access_token).status_code == 400)
        check('新申请确认码可独立消费', post('email-verification/confirm',
            {'code': replacement}, token.access_token).status_code == 200)

        actor, password, token = fixture()
        check('密钥轮换测试申请受理', post('email-verification/request',
            {'current_password': password}, token.access_token).status_code == 202)
        code = received_code(sink)
        with override_settings(SECRET_KEY=secrets.token_urlsafe(60)):
            check('服务器密钥轮换后旧确认码失效', post('email-verification/confirm',
                {'code': code}, token.access_token).status_code == 400)
        actor.refresh_from_db()
        check('密钥轮换失败不会误标记邮箱已验证', not actor.email_verified)

        actor, password, token = fixture()
        old_email = actor.email
        check('邮箱改回测试申请受理', post('email-verification/request',
            {'current_password': password}, token.access_token).status_code == 202)
        code = received_code(sink)
        for email in [uuid.uuid4().hex + '@example.test', old_email]:
            actor.refresh_from_db()
            response = client_for(token.access_token).patch('/api/v1/auth/profile/',
                {'email': email, 'profile_version': actor.profile_version}, format='json')
            check('邮箱改动保留正常资料编辑', response.status_code == 200)
        check('邮箱改回原值也不能恢复旧确认码', post('email-verification/confirm',
            {'code': code}, token.access_token).status_code == 400)

        actor, password, token = fixture()
        sink.reject = True
        check('失败上限测试申请异步受理', post('email-verification/request',
            {'current_password': password}, token.access_token).status_code == 202)
        challenge = EmailChallenge.objects.get(user=actor)
        event = OutboxEvent.objects.get(topic='auth.email', payload__challenge_id=str(challenge.pk))
        for _ in range(4):
            OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now() - timedelta(seconds=1))
            dispatch_outbox()
        sink.reject_delay = 0.2
        OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now() - timedelta(seconds=1))
        parallel([lambda: dispatch_outbox(), lambda: dispatch_outbox()])
        sink.reject_delay = 0
        event.refresh_from_db()
        check('SMTP 第五次失败并发派发也不超过上限', event.status == 'failed' and event.attempts == 5)
        sink.reject = False
        OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now() - timedelta(seconds=1))
        dispatch_outbox()
        event.refresh_from_db()
        check('达到失败上限后恢复SMTP也不会继续发送旧邮件', event.attempts == 5 and sink.messages.empty())

        events = list(OutboxEvent.objects.filter(topic='auth.email', payload__challenge_id__in=[str(pk) for pk in
            EmailChallenge.objects.filter(user_id__in=CREATED).values_list('id', flat=True)]).values())
        check('邮件事件只携带challenge_id', all(set(event['payload']) == {'challenge_id'} for event in events))
        persisted = json.dumps({'events': events,
            'challenges': list(EmailChallenge.objects.filter(user_id__in=CREATED).values()),
            'audit': list(OperationLog.objects.filter(user_id__in=CREATED).values())}, default=str)
        check('原始确认码与邮件签名均不持久化到挑战/事件/审计',
              all(code not in persisted and code.split('.')[1] not in persisted for code in CODES))
        with override_settings(AUTH_EMAIL_ENABLED=False):
            config = client_for().get('/api/v1/auth/recovery/config/')
            check('关闭邮件能力匿名配置隐藏SMTP详情', config.status_code == 200
                  and config.json()['data'] == {'enabled': False}
                  and config['Cache-Control'] == 'private, no-store')
            check('关闭邮件能力申请返回503', post('recovery/request',
                {'username': actor.username, 'email': actor.email}).status_code == 503)
finally:
    sink.shutdown()
    sink.server_close()
    thread.join(timeout=5)
    assert not thread.is_alive(), 'SMTP 线程未正常停止'
print('邮箱 PostgreSQL/Redis/SMTP 验收通过：' + str(len(CHECKS)) + ' 项；本地 SMTP 线程与端口已释放')
