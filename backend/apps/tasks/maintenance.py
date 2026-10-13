"""维护任务白名单、参数与跨 worker 排他锁。"""
from contextlib import contextmanager
from functools import wraps
import hashlib
import threading

from django.db import connection
from rest_framework.exceptions import ValidationError

JOBS = {
    'files': {'task': 'tasks.cleanup_soft_deleted_files', 'name': '清理软删除文件',
              'schedule': 'AdminCore 每日软删除文件清理', 'dependencies': ['tasks', 'files']},
    'notifications': {'task': 'tasks.cleanup_expired_notifications', 'name': '清理过期通知',
                      'schedule': 'AdminCore 每日已读通知清理', 'dependencies': ['tasks', 'notifications']},
}
_test_locks = {key: threading.RLock() for key in JOBS}


def validate_options(key, options):
    allowed = {'dry_run', 'batch_size'} if key == 'files' else {'dry_run'}
    if not isinstance(options, dict) or set(options) - allowed:
        raise ValidationError('任务参数包含未注册字段')
    options = dict(options)
    options.setdefault('dry_run', False)
    if type(options['dry_run']) is not bool:
        raise ValidationError('dry_run 必须为布尔值')
    if key == 'files':
        options.setdefault('batch_size', 100)
        if type(options['batch_size']) is not int or not 1 <= options['batch_size'] <= 100:
            raise ValidationError('batch_size 必须为 1–100 的整数')
    return options


@contextmanager
def maintenance_lock(key):
    """PostgreSQL 会话锁：不把慢存储操作包在长数据库事务中。"""
    if connection.vendor == 'postgresql':
        identifier = int.from_bytes(hashlib.sha256(('admincore:maintenance:' + key).encode()).digest()[:8], 'big', signed=True)
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', [identifier])
            acquired = cursor.fetchone()[0]
        try:
            yield acquired
        finally:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_unlock(%s)', [identifier])
    else:
        # 仅本机 SQLite 单进程测试使用；部署使用 PostgreSQL。
        lock = _test_locks[key]
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()


def exclusive(key):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            from apps.core.modules import require_task
            require_task(JOBS[key]['task'])
            with maintenance_lock(key) as acquired:
                if not acquired:
                    from .models import TaskRecord
                    result = {'skipped': True, 'reason': 'overlap'}
                    record = TaskRecord.objects.create(name=JOBS[key]['name'], task_type='cleanup',
                                                       related_resource='maintenance:' + key)
                    record.mark_success(result)
                    return result
                return function(*args, **kwargs)
        return run
    return decorate


def valid_preview(key, record_id, user_id):
    from datetime import timedelta
    from django.utils import timezone
    from apps.core.system_config import config_value
    from .models import MaintenanceRequest
    preview = MaintenanceRequest.objects.select_related('record').filter(
        pk=record_id, key=key, record__creator_id=user_id, record__status='success',
        record__completed_at__gte=timezone.now() - timedelta(minutes=15), options__dry_run=True,
    ).first()
    policy = 'files.retention_days' if key == 'files' else 'notifications.retention_days'
    return bool(preview and isinstance(preview.record.result, dict)
                and preview.record.result.get('dry_run') is True
                and preview.record.result.get('retention_days') == config_value(policy))
