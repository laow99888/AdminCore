"""仅隔离 foundation 库：真实 PostgreSQL 会话锁、重复领取与释放。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import uuid

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.utils import timezone

from apps.notifications.models import Notification
from apps.tasks.maintenance import maintenance_lock
from apps.tasks.models import MaintenanceRequest, TaskRecord
from apps.tasks.tasks import cleanup_expired_notifications, run_maintenance

assert connection.settings_dict['NAME'] == 'foundation', '只允许隔离验收数据库'
assert connection.vendor == 'postgresql'
user = get_user_model().objects.create_superuser('maintenance-' + uuid.uuid4().hex[:12], password=uuid.uuid4().hex)
records = []
held = threading.Event()
release = threading.Event()


def holder():
    try:
        with maintenance_lock('notifications') as acquired:
            assert acquired
            held.set()
            assert release.wait(20)
    finally:
        connections.close_all()


def execute(identifier):
    try:
        return run_maintenance(str(identifier))
    finally:
        connections.close_all()


try:
    note = Notification.objects.create(recipient=user, title='隔离过期通知', is_read=True)
    Notification.objects.filter(pk=note.pk).update(read_at=timezone.now() - timedelta(days=100))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(holder)
        assert held.wait(10)
        try:
            result = cleanup_expired_notifications(dry_run=True)
            assert result == {'skipped': True, 'reason': 'overlap'}
            records += list(TaskRecord.objects.filter(related_resource='maintenance:notifications', result=result).values_list('pk', flat=True))
            assert Notification.objects.filter(pk=note.pk).exists()
        finally:
            release.set()
        future.result(timeout=10)
    record = TaskRecord.objects.create(name='并发领取', task_type='cleanup', creator=user, related_resource='maintenance:notifications')
    records.append(record.pk)
    MaintenanceRequest.objects.create(record=record, key='notifications', options={'dry_run': True}, session_version=user.session_version)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(execute, [record.pk] * 4))
    assert sum(result.get('dry_run') is True for result in results) == 1, results
    assert sum(result.get('reason') == 'already_claimed' for result in results) == 3, results
    record.refresh_from_db()
    assert record.status == 'success' and record.result['eligible_notifications'] >= 1
    assert Notification.objects.filter(pk=note.pk).exists()
    with maintenance_lock('notifications') as acquired:
        assert acquired, '执行成功后已释放会话锁'
    print('PostgreSQL：两连接排他、重叠跳过、四次重复领取仅执行一次、成功释放锁通过')
finally:
    release.set()
    TaskRecord.objects.filter(pk__in=records).delete()
    user.delete()
