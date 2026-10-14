"""仅在 foundation PostgreSQL 中运行：真实 SMTP、并发、版本及授权终止验收。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email import policy
from email.parser import BytesParser
import queue
import secrets
import socketserver
from threading import Barrier, Thread
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.sessions import issue_session
from apps.core.models import OutboxEvent
from apps.core.tasks import dispatch_outbox
from apps.logs.models import OperationLog
from apps.notifications.models import MessageTemplate, MessageDelivery, Notification

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
User = get_user_model()
CHECKS = []
BASE = '/api/v1/notifications/templates/'
DELIVERIES = '/api/v1/notifications/deliveries/'


def check(label, condition):
    assert condition, label
    CHECKS.append(label)
    print('通过：通用通知 ' + label, flush=True)


class MailSink(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self):
        self.messages = queue.Queue()
        self.reject = False
        super().__init__(('127.0.0.1', 0), SMTPHandler)


class SMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        self.wfile.write(b'220 isolated fixture\r\n')
        while line := self.rfile.readline(65537):
            verb = line.split(b' ', 1)[0].strip().upper()
            if verb in (b'EHLO', b'HELO', b'MAIL', b'RCPT', b'RSET', b'NOOP'):
                self.wfile.write(b'250 OK\r\n')
            elif verb == b'DATA':
                if self.server.reject:
                    self.wfile.write(b'451 private-fixture-address-and-password\r\n')
                    continue
                self.wfile.write(b'354 continue\r\n')
                parts = []
                while (part := self.rfile.readline(65537)) not in (b'.\r\n', b''):
                    parts.append(part[1:] if part.startswith(b'..') else part)
                self.server.messages.put(b''.join(parts))
                self.wfile.write(b'250 accepted\r\n')
            elif verb == b'QUIT':
                self.wfile.write(b'221 bye\r\n')
                return
            else:
                self.wfile.write(b'502 unsupported\r\n')


def client():
    api = APIClient(HTTP_HOST='backend')
    api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    return api


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


def send(channel, key=None):
    response = client().post(BASE + str(template.pk) + '/send/', {
        'revision': template.revision, 'recipient_ids': [str(recipient.pk)], 'channels': [channel],
        'values': {'name': '私密正文 fixture'}}, format='json', HTTP_IDEMPOTENCY_KEY=key or secrets.token_hex(20))
    check('发送登记成功', response.status_code == 202)
    return MessageDelivery.objects.get(pk=response.json()['data']['delivery_ids'][0])


actor = User.objects.create_superuser('msg-admin-' + secrets.token_hex(5), 'msg-admin-' + secrets.token_hex(5) + '@example.test', secrets.token_urlsafe(40))
recipient = User.objects.create_user('msg-user-' + secrets.token_hex(5), 'msg-user-' + secrets.token_hex(5) + '@example.test', secrets.token_urlsafe(40))
recipient.verified_email = recipient.email
recipient.save(update_fields=['verified_email'])
token = issue_session(actor)
sink = MailSink()
thread = Thread(target=sink.serve_forever, name='isolated-message-smtp', daemon=True)
thread.start()
try:
    with override_settings(NOTIFICATION_EMAIL_ENABLED=True, EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='127.0.0.1', EMAIL_PORT=sink.server_address[1], EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='',
        EMAIL_USE_TLS=False, EMAIL_USE_SSL=False, EMAIL_TIMEOUT=3, DEFAULT_FROM_EMAIL='fixture@example.test'), \
        patch('apps.core.events._dispatch_after_commit'):
        draft = {'code': 'fixture-' + secrets.token_hex(5), 'name': '通知验收', 'enabled': True, 'revision': 0,
                 'subject': 'Hello ${name}', 'body': '原版本 ${name}', 'variables': ['name']}
        response = client().post(BASE, draft, format='json')
        check('新模板与初始版本原子创建', response.status_code == 201)
        template = MessageTemplate.objects.get(pk=response.json()['data']['id'])
        row = send('email')
        updated = {**draft, 'revision': 1, 'body': '新版 ${name}'}
        statuses = parallel([lambda: client().patch(BASE + str(template.pk) + '/', updated, format='json').status_code for _ in range(2)])
        check('并发编辑仅一次成功，冲突不覆盖', sorted(statuses) == [200, 409])
        template.refresh_from_db()
        check('旧模板版本保持不变', template.revision == 2 and template.versions.count() == 2 and row.version.number == 1)
        parallel([dispatch_outbox, dispatch_outbox])
        message = BytesParser(policy=policy.default).parsebytes(sink.messages.get(timeout=5))
        row.refresh_from_db()
        check('真实 SMTP Unicode 字节与旧正文一致', message.get_body(preferencelist=('plain',)).get_content().strip() == '原版本 私密正文 fixture')
        check('真实 SMTP 收件地址正确及固定 Message-ID', str(message['To']) == recipient.email and str(row.pk) in str(message['Message-ID']))
        check('并发派发恰好一次 SMTP 接收', row.status == 'succeeded' and row.attempts == 1 and sink.messages.empty())
        dispatch_outbox()
        check('成功记录不能再次发送', sink.messages.empty() and client().post(DELIVERIES + str(row.pk) + '/retry/', {}, format='json').status_code == 400)
        payload = client().get(DELIVERIES + str(row.pk) + '/').json()['data']
        check('诊断只读详情无正文、邮箱或会话', not {'body', 'subject', 'email_binding', 'actor_session_id'} & set(payload) and recipient.email not in str(payload))
        key = secrets.token_hex(20)
        inapp = send('inapp', key)
        send('inapp', key)
        parallel([dispatch_outbox, dispatch_outbox])
        check('站内幂等登记且消费去重', Notification.objects.filter(recipient=recipient, title='Hello 私密正文 fixture').count() == 1)
        check('当前版本独立记录', inapp.version.number == 2)

        recipient.is_staff = True
        recipient.save(update_fields=['is_staff'])
        peer_token = issue_session(recipient)

        def mutual_send(access, recipient_id):
            api = APIClient(HTTP_HOST='backend')
            api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(access))
            return api.post(BASE + str(template.pk) + '/send/', {'revision': 2,
                'recipient_ids': [str(recipient_id)], 'channels': ['inapp'], 'values': {'name': 'mutual'}},
                format='json', HTTP_IDEMPOTENCY_KEY=secrets.token_hex(20)).status_code

        check('两个管理员互发保持相同用户锁顺序', parallel([
            lambda: mutual_send(token.access_token, recipient.pk),
            lambda: mutual_send(peer_token.access_token, actor.pk)]) == [202, 202])
        parallel([dispatch_outbox, dispatch_outbox])
        check('互发并发消费无死锁或遗漏', Notification.objects.filter(title='Hello mutual', recipient__in=[actor, recipient]).count() == 2)

        sink.reject = True
        failed = send('email')
        event = OutboxEvent.objects.get(event_key='message:' + str(failed.pk))
        for number in range(1, 6):
            OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now()-timedelta(seconds=1))
            parallel([dispatch_outbox, dispatch_outbox])
            failed.refresh_from_db(); event.refresh_from_db()
            check('SMTP 故障并发有限重试 ' + str(number), failed.attempts == number and event.attempts == number and failed.status == 'failed' and event.status == 'failed')
            check('SMTP 私密详情不进入诊断 ' + str(number), failed.last_error == event.last_error == 'channel_delivery_failed')
            if number == 1:
                retry = client().post(DELIVERIES + str(failed.pk) + '/retry/', {}, format='json')
                check('人工重试复核当前身份且不重置次数', retry.status_code == 200 and retry.json()['data']['attempts'] == 1)
        sink.reject = False
        OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now()-timedelta(seconds=1))
        dispatch_outbox(); failed.refresh_from_db()
        check('五次用尽后恢复 SMTP 也不重放', failed.attempts == 5 and sink.messages.empty() and client().post(DELIVERIES + str(failed.pk) + '/retry/', {}, format='json').status_code == 400)
        check('通用事件重试不能绕过投递入口', client().post('/api/v1/reliability/events/' + str(event.pk) + '/retry/', {}, format='json').status_code == 409)

        pending = send('email')
        recipient.email = 'changed-' + secrets.token_hex(5) + '@example.test'
        recipient.save(update_fields=['email'])
        dispatch_outbox(); pending.refresh_from_db()
        check('邮箱改变后待发终止且不向新邮箱发送', pending.status == 'terminated' and pending.last_error == 'recipient_email_changed' and sink.messages.empty())
        pending = send('inapp')
        from apps.auth_app.models import AuthSession
        AuthSession.objects.filter(pk=pending.actor_session_id).update(revoked_at=timezone.now())
        dispatch_outbox(); pending.refresh_from_db()
        check('原发送会话撤销后待发终止', pending.status == 'terminated' and pending.last_error == 'sender_session_revoked')
        token = issue_session(actor)
        with patch('apps.notifications.message_services.write_audit', side_effect=RuntimeError('isolated audit failure')):
            count = MessageDelivery.objects.count()
            response = client().post(BASE + str(template.pk) + '/send/', {'revision': 2, 'recipient_ids': [str(recipient.pk)], 'channels': ['inapp'], 'values': {'name': 'rollback'}}, format='json', HTTP_IDEMPOTENCY_KEY=secrets.token_hex(20))
        check('审计失败回滚投递和可靠事件', response.status_code == 500 and MessageDelivery.objects.count() == count)
        logs = OperationLog.objects.filter(user=actor, resource__in=['message_template', 'message_delivery'])
        check('安全审计无正文或实际地址', recipient.email not in str(list(logs.values())) and '私密正文' not in str(list(logs.values())))
        from apps.tasks.models import TaskRecord
        from apps.tasks.reliability import deliver_failure
        from apps.core.models import SystemConfig
        actor.verified_email = actor.email
        actor.save(update_fields=['verified_email'])
        SystemConfig.objects.update_or_create(key='tasks.failure_email', defaults={'value': 1})
        alert_record = TaskRecord.objects.create(name='private alert title', creator=actor)
        alert_record.mark_failed('private original error')
        deliver_failure({'record_id': str(alert_record.pk)})
        alert = BytesParser(policy=policy.default).parsebytes(sink.messages.get(timeout=5))
        check('任务告警真实 SMTP 接收且无原始业务内容', str(alert_record.pk) in str(alert['Message-ID'])
              and 'private alert title' not in alert.as_string() and 'private original error' not in alert.as_string()
              and 'Bcc' not in alert)
        sink.reject = True
        try:
            deliver_failure({'record_id': str(alert_record.pk)})
            check('任务告警 SMTP 451 不伪装成功', False)
        except Exception as error:
            check('任务告警 SMTP 451 显式失败', type(error).__name__ == 'SMTPDataError')
        finally:
            sink.reject = False
            SystemConfig.objects.filter(key='tasks.failure_email').delete()
finally:
    sink.shutdown(); sink.server_close(); thread.join(timeout=5)
    assert not thread.is_alive(), 'SMTP 线程未停止'
print('通用通知 PostgreSQL/SMTP 验收通过：' + str(len(CHECKS)) + ' 项；SMTP 线程和端口已释放', flush=True)
