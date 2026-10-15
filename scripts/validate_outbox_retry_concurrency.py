"""仅 foundation：真实消费者 event→actor 与真实 JWT 人工重试 actor→event。

可将本文件 UTF-8 内容编码后通过 manage.py shell exec(base64.b64decode(...)) 执行。
SQL wrapper 只安排等待顺序，不替换授权、会话、事件查询或消费业务。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as datetime_timezone
from threading import Event
from time import monotonic, sleep
from uuid import uuid4, UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.sessions import issue_session
from apps.core.models import OutboxEvent
from apps.core.modules import module_enabled
from apps.core.system_config import config_value
from apps.core.tasks import dispatch_outbox
from apps.logs.models import OperationLog
from apps.notifications.models import Notification
from apps.tasks.models import TaskRecord

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connection.vendor == 'postgresql', '必须使用 PostgreSQL'
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    assert cursor.fetchone()[0] == 'foundation'
assert module_enabled('tasks') and module_enabled('notifications'), '需要启用任务及通知模块'
assert not config_value('tasks.failure_email'), '隔离验收必须禁用任务故障邮件'

User = get_user_model()
prefix = 'outbox_lock_' + uuid4().hex[:12]
actor = User.objects.create_superuser(prefix, password=uuid4().hex + uuid4().hex,
    id=UUID(int=uuid4().int & ((1 << 96) - 1)), must_change_password=False)
token = str(issue_session(actor).access_token)
record = TaskRecord.objects.create(name=prefix, creator=actor, status='failed', task_type='other')
event = OutboxEvent.objects.create(topic='task.failed', event_key=prefix,
    payload={'record_id': str(record.pk)}, status='failed', available_at=timezone.now() - timedelta(days=1))
# limit=1 必须选中本脚本事件，避免派发其他夹具的事件。
OutboxEvent.objects.filter(pk=event.pk).update(created_at=datetime(1900, 1, 1, tzinfo=datetime_timezone.utc))
assert OutboxEvent.objects.filter(status__in=['pending', 'failed'], available_at__lte=timezone.now()).order_by('created_at').first().pk == event.pk
assert actor.pk in list(User.objects.filter(is_active=True, is_staff=True).order_by('pk').values_list('pk', flat=True)[:100])

actor_locked, consumer_about_actor = Event(), Event()
backend_pids = {}


def configure(label):
    connections.close_all()
    with connection.cursor() as cursor:
        cursor.execute("SET lock_timeout = '6s'")
        cursor.execute("SET statement_timeout = '12s'")
        cursor.execute('SELECT pg_backend_pid()')
        backend_pids[label] = cursor.fetchone()[0]


def retry_observer(execute, sql, params, many, context):
    if 'FOR UPDATE NOWAIT' in sql and ('"' + OutboxEvent._meta.db_table + '"') in sql:
        # 此时 authorize_write 已真实锁定 actor 和原 JWT 设备。
        actor_locked.set()
        assert consumer_about_actor.wait(10), '消费者应先锁事件，再准备锁接收人'
        deadline = monotonic() + 5
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_blocking_pids(%s)', [backend_pids['consumer']])
                if backend_pids['retry'] in cursor.fetchone()[0]:
                    break
            sleep(0.01)
        else:
            raise AssertionError('必须观察到消费者真实等待 retry 的 actor 行锁')
    return execute(sql, params, many, context)


def consumer_observer(execute, sql, params, many, context):
    if 'FOR UPDATE' in sql and ('"' + User._meta.db_table + '"') in sql:
        consumer_about_actor.set()
    return execute(sql, params, many, context)


def retry():
    try:
        configure('retry')
        client = APIClient(HTTP_HOST='localhost')
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        with connection.execute_wrapper(retry_observer):
            return client.post(f'/api/v1/reliability/events/{event.pk}/retry/')
    finally:
        connections.close_all()


def consume():
    try:
        configure('consumer')
        with connection.execute_wrapper(consumer_observer):
            return dispatch_outbox(limit=1)
    finally:
        connections.close_all()


try:
    with ThreadPoolExecutor(max_workers=2) as pool:
        retry_future = pool.submit(retry)
        assert actor_locked.wait(10), '人工重试必须先完成真实身份授权并持有 actor 锁'
        consumer_future = pool.submit(consume)
        response = retry_future.result(timeout=20)
        consumed = consumer_future.result(timeout=20)
    assert len(set(backend_pids.values())) == 2
    assert response.status_code == 409 and response.json()['message'] == '事件正在处理，请稍后重试', response.status_code
    assert consumed == {'processed': 1, 'failed': 0}, consumed
    event.refresh_from_db()
    assert event.status == 'succeeded' and event.attempts == 1
    assert Notification.objects.filter(recipient=actor, data__record_id=str(record.pk)).count() == 1
    assert not OperationLog.objects.filter(resource='outbox_event', resource_id=str(event.pk)).exists()
    print('通过：真实 PG 观察到 consumer event→actor 等待，JWT retry actor→event NOWAIT 返回409并释放身份锁，消费者完成且仅投递一次', flush=True)
except BaseException:
    print('失败证据保留：actor=' + str(actor.pk) + ' event=' + str(event.pk) + ' record=' + str(record.pk), flush=True)
    raise
else:
    # 只删除本次 UUID 明确标识的夹具及其站内通知，不触碰其他事件或原始文件。
    Notification.objects.filter(data__record_id=str(record.pk)).delete()
    event.delete()
    record.delete()
    actor.delete()
    print('通过：已清理本脚本专属事件、任务、用户和站内通知；无线程连接遗留', flush=True)
