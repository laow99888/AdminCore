"""仅在 validate_foundation 创建的 PostgreSQL 隔离库内执行。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
import secrets
import time
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.sessions import issue_session
from apps.files.models import FileModel
from apps.logs.models import LoginLog, OperationLog
from apps.tasks import lifecycle
from apps.tasks.models import TaskRecord
from apps.tasks.models import ImportBatch, ImportExecution
from apps.tasks.reliability import policy
from apps.data_io.execution import digest

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
user = get_user_model().objects.get(username='admin')
token = str(issue_session(user).access_token)


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print('通过：历史清理 ' + label, flush=True)


def fixture():
    file = FileModel.objects.create(original_name='fixture.csv', file=ContentFile(b'username\nu1', name='fixture.csv'),
                                    purpose='import', uploader=user, size=11)
    FileModel.objects.filter(pk=file.pk).update(created_at=timezone.now() - timedelta(days=400))
    task = TaskRecord.objects.create(name='清理竞争夹具', task_type='import', status='failed', creator=user,
        related_resource='users', result={'file_id': str(file.pk)}, completed_at=timezone.now() - timedelta(days=100))
    batch = ImportBatch.objects.create(source=file, source_sha256=digest(file.file), resource='users', active_record=task)
    ImportExecution.objects.create(record=task, batch=batch, policy=policy('import'), session_version=user.session_version)
    return file, task


def retry(task):
    client = APIClient(HTTP_HOST='backend', REMOTE_ADDR='127.0.6.1')
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
    return client.post(f'/api/v1/data-io/import/{task.pk}/', {}, format='json')


def isolated(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    finally:
        connections.close_all()


# 真实 PostgreSQL 上验证 JSON/UUID 相关子查询、预览与本地对象删除。
log = LoginLog.objects.create(username='lifecycle-' + secrets.token_hex(6), status='failed', ip_address='127.0.6.1')
LoginLog.objects.filter(pk=log.pk).update(created_at=timezone.now() - timedelta(days=400))
file, task = fixture()
assert lifecycle.clean(dry_run=True)['eligible']['imports'] == 1
check('预览保留日志、文件行和本地字节', LoginLog.objects.filter(pk=log.pk).exists() and file.file.storage.exists(file.file.name))
assert lifecycle.clean()['deleted']['imports'] == 1
from apps.core.tasks import dispatch_outbox
dispatch_outbox()
check('实际删除日志与对象，保留任务及摘要审计', not LoginLog.objects.filter(pk=log.pk).exists()
      and not file.file.storage.exists(file.file.name) and TaskRecord.objects.filter(pk=task.pk).exists()
      and OperationLog.objects.filter(resource='lifecycle', description__contains=str(file.pk)).exists())

# 清理先持锁：重试等待后明确告知源文件不可用，不产生悬空导入任务。
file, task = fixture()
locked, release = Event(), Event()
original_check = lifecycle.import_in_use


def hold_cleanup(identifier, cutoff):
    locked.set()
    assert release.wait(10)
    return original_check(identifier, cutoff)


with patch('apps.tasks.lifecycle.import_in_use', hold_cleanup):
    with ThreadPoolExecutor(max_workers=2) as pool:
        cleaning = pool.submit(isolated, lifecycle.clean)
        try:
            assert locked.wait(10)
            retrying = pool.submit(isolated, retry, task)
            time.sleep(0.2)
            check('清理先持文件行锁时重试等待', not retrying.done())
        finally:
            release.set()
        assert cleaning.result(timeout=15)['deleted']['imports'] == 1
        check('清理先完成后重试返回明确 400', retrying.result(timeout=15).status_code == 400)
        assert not TaskRecord.objects.filter(task_type='import', status='pending', result__file_id=str(file.pk)).exists()

# 重试先持锁：清理等待，在锁内复核新任务，不能删除正在使用的源文件。
file, task = fixture()
record = TaskRecord.objects.create(name='并发清理', task_type='cleanup', status='running')
locked, release = Event(), Event()
original_create = TaskRecord.objects.create


def hold_retry(**values):
    row = original_create(**values)
    if values.get('name', '').endswith('（接续）'):
        locked.set()
        assert release.wait(10)
    return row


with patch.object(TaskRecord.objects, 'create', side_effect=hold_retry):
    with ThreadPoolExecutor(max_workers=2) as pool:
        retrying = pool.submit(isolated, retry, task)
        try:
            assert locked.wait(10)
            cleaning = pool.submit(isolated, lifecycle.clean, record=record)
            time.sleep(0.2)
            check('重试先持文件行锁时清理等待', not cleaning.done())
        finally:
            release.set()
        assert retrying.result(timeout=15).status_code == 202
        result = cleaning.result(timeout=15)
        check('锁后复核新任务并保留对象', result['deleted']['imports'] == 0 and result['protected_imports'] == 1
              and FileModel.objects.filter(pk=file.pk).exists() and file.file.storage.exists(file.file.name))
check('仍在使用的导入源不会阻塞其他过期文件', lifecycle.clean()['protected_imports'] == 1)
