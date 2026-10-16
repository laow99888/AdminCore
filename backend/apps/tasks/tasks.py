"""
Celery 异步任务定义

启动 worker 后自动发现：
    celery -A config worker -l info
"""

import logging

from celery import shared_task
from apps.tasks.routing import RegisteredPolicyTask
from django.conf import settings
from django.utils import timezone
from .maintenance import exclusive

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='tasks.cleanup_lifecycle', soft_time_limit=270, time_limit=300, base=RegisteredPolicyTask)
@exclusive('lifecycle')
def cleanup_lifecycle(self, dry_run=False, _record=None, _expected_retention=None):
    from .lifecycle import clean
    if _record is None:
        from .models import TaskRecord
        from .routing import record_scheduled_policy
        _record = TaskRecord.objects.create(name='清理历史日志与导入源文件', task_type='cleanup',
            status='running', started_at=timezone.now(), related_resource='maintenance:lifecycle',
            celery_task_id=self.request.id or '')
        record_scheduled_policy(_record, 'lifecycle', {'dry_run': dry_run}, self.request)
    return clean(dry_run=dry_run, record=_record, expected_policy=_expected_retention,
                 celery_task_id=self.request.id or '')


@shared_task(bind=True, name='tasks.request_backup')
def request_backup(self, dry_run=False, _record=None):
    """Celery 仅登记停写备份请求，不取得 Docker 控制权限。"""
    from apps.core.modules import require_task
    from .backup import register
    require_task(self.name)
    return register(record=_record, dry_run=dry_run, celery_task_id=self.request.id or '')


@shared_task(bind=True, name='tasks.cleanup_soft_deleted_files', soft_time_limit=270, time_limit=300, base=RegisteredPolicyTask)
@exclusive('files')
def cleanup_soft_deleted_files(self, dry_run=False, batch_size=100, _record=None, _expected_retention=None):
    """物理删除超过保留期的软删除文件（默认保留 30 天，由 beat 每日调度）"""
    from apps.core.modules import require_task
    require_task(self.name)
    from datetime import timedelta

    from apps.files.models import FileModel
    from apps.tasks.models import TaskRecord

    record = _record or TaskRecord.objects.create(
        name='清理软删除文件',
        task_type='cleanup',
        celery_task_id=self.request.id or '',
        status='running',
        started_at=timezone.now(),
        related_resource='maintenance:files',
    )
    purged = 0
    if _record is None:
        from .routing import record_scheduled_policy
        record_scheduled_policy(record, 'files', {'dry_run': dry_run, 'batch_size': batch_size}, self.request)
    try:
        if type(dry_run) is not bool or type(batch_size) is not int or not 1 <= batch_size <= 100:
            raise ValueError('dry_run 必须为布尔值，batch_size 必须为 1–100 的整数')
        from apps.core.system_config import config_value
        retention_days = config_value('files.retention_days')
        if _expected_retention is not None and retention_days != _expected_retention:
            raise ValueError('preview_policy_changed')
        cutoff = timezone.now() - timedelta(days=retention_days)
        expired = FileModel.objects.filter(is_deleted=True, deleted_at__lt=cutoff)
        if dry_run:
            from django.db.models import Sum
            result = {'purged_files': 0, 'eligible_files': expired.count(),
                      'eligible_bytes': expired.aggregate(total=Sum('size'))['total'] or 0,
                      'retention_days': retention_days, 'dry_run': True}
            record.mark_success(result=result)
            return result
        # 固定截止时间、按主键游标分批；不一次性加载所有过期文件。
        cursor = None
        while True:
            query = expired.filter(pk__gt=cursor) if cursor is not None else expired
            batch = list(query.order_by('pk')[:batch_size])
            if not batch:
                break
            for file_obj in batch:
                def audit(row):
                    import json
                    from apps.logs.models import OperationLog
                    OperationLog.objects.create(
                        user=None, action='delete', resource='file', resource_id=str(row.pk),
                        ip_address='127.0.0.1', description=json.dumps({
                            'operation': 'retention_purge', 'original_name': row.original_name,
                            'task_record_id': str(record.pk), 'before': {
                                'is_deleted': row.is_deleted, 'deleted_at': row.deleted_at.isoformat(),
                                'lifecycle_version': row.lifecycle_version,
                            }, 'after': None,
                        }, ensure_ascii=False),
                    )
                purged += file_obj.hard_delete(deleted_before=cutoff, audit=audit)
            cursor = batch[-1].pk
        from apps.files.resumable import cleanup_expired_sessions
        expired_uploads = cleanup_expired_sessions(limit=batch_size)
        record.mark_success(result={'purged_files': purged, 'expired_uploads': expired_uploads,
                                    'retention_days': retention_days})
        logger.info('Cleanup purged %d expired files', purged)
        return {'purged_files': purged, 'expired_uploads': expired_uploads}
    except Exception as exc:
        record.result = {'purged_files': purged}
        record.save(update_fields=['result'])
        record.mark_failed(error=type(exc).__name__)
        logger.exception('Cleanup soft deleted files failed')
        raise


@shared_task(bind=True, name='tasks.cleanup_expired_notifications', soft_time_limit=270, time_limit=300, base=RegisteredPolicyTask)
@exclusive('notifications')
def cleanup_expired_notifications(self, dry_run=False, _record=None, _expected_retention=None):
    """清理超过保留期的已读通知（默认保留 90 天）"""
    from apps.core.modules import require_task
    require_task(self.name)
    from datetime import timedelta

    from apps.notifications.models import Notification
    from apps.tasks.models import TaskRecord

    record = _record or TaskRecord.objects.create(
        name='清理过期通知',
        task_type='cleanup',
        celery_task_id=self.request.id or '',
        status='running',
        started_at=timezone.now(),
        related_resource='maintenance:notifications',
    )
    if _record is None:
        from .routing import record_scheduled_policy
        record_scheduled_policy(record, 'notifications', {'dry_run': dry_run}, self.request)
    try:
        if type(dry_run) is not bool:
            raise ValueError('dry_run 必须为布尔值')
        from apps.core.system_config import config_value
        retention_days = config_value('notifications.retention_days')
        if _expected_retention is not None and retention_days != _expected_retention:
            raise ValueError('preview_policy_changed')
        cutoff = timezone.now() - timedelta(days=retention_days)
        expired = Notification.objects.filter(is_read=True, read_at__lt=cutoff)
        if dry_run:
            result = {'deleted_notifications': 0, 'eligible_notifications': expired.count(),
                      'retention_days': retention_days, 'dry_run': True}
            record.mark_success(result)
            return result
        deleted, _ = expired.delete()
        record.mark_success(result={'deleted_notifications': deleted})
        return {'deleted_notifications': deleted}
    except Exception as exc:
        record.mark_failed(error=type(exc).__name__)
        logger.exception('Cleanup expired notifications failed')
        raise


@shared_task(bind=True, name='tasks.run_maintenance', soft_time_limit=270, time_limit=300,
             acks_late=True, reject_on_worker_lost=True, base=RegisteredPolicyTask)
def run_maintenance(self, record_id):
    """重复投递只领取一次；执行前重新检查账户、权限、会话和模块。"""
    from datetime import timedelta
    from django.db import transaction
    from apps.core.modules import task_enabled
    from apps.permissions.permissions import has_permission_code
    from .maintenance import JOBS, maintenance_lock, validate_options, valid_preview
    from .models import MaintenanceRequest, TaskRecord

    request = MaintenanceRequest.objects.select_related('record__creator').filter(pk=record_id).first()
    if not request or request.record.status != 'pending':
        return {'skipped': True, 'reason': 'already_claimed'}
    with transaction.atomic():
        from django.contrib.auth import get_user_model
        # 与取消/设备撤销一致：先用户、原设备，再任务，避免读取过期授权。
        user = get_user_model().objects.select_for_update().filter(pk=request.record.creator_id).first()
        if request.session_id:
            from apps.auth_app.models import AuthSession
            AuthSession.objects.select_for_update().filter(pk=request.session_id).first()
        record = TaskRecord.objects.select_for_update().get(pk=record_id)
        if record.status != 'pending':
            return {'skipped': True, 'reason': 'already_claimed'}
        from .reliability import valid_execution
        if (not user or not user.is_active or user.must_change_password
                or not (user.is_staff or user.is_superuser)
                or user.session_version != request.session_version
                or not has_permission_code(user, 'schedule:run')
                or not task_enabled(JOBS[request.key]['task']) or not valid_execution(request, user)):
            record.mark_failed('execution_not_authorized')
            return {'rejected': True}
        if record.created_at < timezone.now() - timedelta(hours=24):
            record.mark_failed('request_expired')
            return {'rejected': True}
        if (request.key != 'backup' and not request.options.get('dry_run')
                and not valid_preview(request.key, request.preview_id, record.creator_id)):
            record.mark_failed('preview_expired_or_policy_changed')
            return {'rejected': True}
        record.celery_task_id = self.request.id or str(record.pk)
        record.save(update_fields=['celery_task_id', 'updated_at'])
        if request.key == 'backup':
            return request_backup(_record=record, **validate_options(request.key, request.options))
        record.mark_started()
    with maintenance_lock(request.key) as acquired:
        if not acquired:
            result = {'skipped': True, 'reason': 'overlap'}
            record.mark_success(result)
            return result
        try:
            expected = TaskRecord.objects.get(pk=request.preview_id).result[
                'policy' if request.key == 'lifecycle' else 'retention_days'] \
                if request.key in {'lifecycle', 'files'} and not request.options.get('dry_run') else None
            function = {'files': cleanup_soft_deleted_files,
                        'notifications': cleanup_expired_notifications,
                        'lifecycle': cleanup_lifecycle}[request.key]
            return function(_record=record, _expected_retention=expected, **validate_options(request.key, request.options))
        except Exception as exc:
            record.mark_failed(type(exc).__name__)
            raise


def recover_lost_maintenance():
    """硬超时/进程中断的结果记为未知，不自动重放删除。"""
    from datetime import timedelta
    from .maintenance import JOBS, maintenance_lock
    from .models import TaskRecord
    for key in JOBS:
        if key == 'backup':
            continue
        with maintenance_lock(key) as acquired:
            if acquired:
                from .models import MaintenanceRequest
                from .reliability import policy
                for record in TaskRecord.objects.filter(related_resource='maintenance:' + key, status='pending',
                    created_at__lt=timezone.now() - timedelta(hours=24))[:100]:
                    record.mark_failed('queue_expired')
                for record in TaskRecord.objects.filter(related_resource='maintenance:' + key, status='running')[:100]:
                    request = MaintenanceRequest.objects.filter(pk=record.pk).first()
                    limits = request.policy if request and request.policy else policy('maintenance')
                    if record.started_at and record.started_at < timezone.now() - timedelta(seconds=limits['hard_timeout'] + 60):
                        record.mark_failed('worker_lost_result_unknown')
