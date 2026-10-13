"""
Celery 异步任务定义

启动 worker 后自动发现：
    celery -A config worker -l info
"""

import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='tasks.cleanup_soft_deleted_files')
def cleanup_soft_deleted_files(self, dry_run=False, batch_size=100):
    """物理删除超过保留期的软删除文件（默认保留 30 天，由 beat 每日调度）"""
    from apps.core.modules import require_task
    require_task(self.name)
    from datetime import timedelta

    from apps.files.models import FileModel
    from apps.tasks.models import TaskRecord

    record = TaskRecord.objects.create(
        name='清理软删除文件',
        task_type='cleanup',
        celery_task_id=self.request.id or '',
        status='running',
        started_at=timezone.now(),
    )
    purged = 0
    try:
        if type(dry_run) is not bool or type(batch_size) is not int or not 1 <= batch_size <= 100:
            raise ValueError('dry_run 必须为布尔值，batch_size 必须为 1–100 的整数')
        from apps.core.system_config import config_value
        retention_days = config_value('files.retention_days')
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
        record.mark_success(result={'purged_files': purged, 'retention_days': retention_days})
        logger.info('Cleanup purged %d expired files', purged)
        return {'purged_files': purged}
    except Exception as exc:
        record.result = {'purged_files': purged}
        record.save(update_fields=['result'])
        record.mark_failed(error=str(exc))
        logger.exception('Cleanup soft deleted files failed')
        raise


@shared_task(bind=True, name='tasks.cleanup_expired_notifications')
def cleanup_expired_notifications(self):
    """清理超过保留期的已读通知（默认保留 90 天）"""
    from apps.core.modules import require_task
    require_task(self.name)
    from datetime import timedelta

    from apps.notifications.models import Notification
    from apps.tasks.models import TaskRecord

    record = TaskRecord.objects.create(
        name='清理过期通知',
        task_type='cleanup',
        celery_task_id=self.request.id or '',
        status='running',
        started_at=timezone.now(),
    )
    try:
        from apps.core.system_config import config_value
        retention_days = config_value('notifications.retention_days')
        cutoff = timezone.now() - timedelta(days=retention_days)
        deleted, _ = Notification.objects.filter(is_read=True, read_at__lt=cutoff).delete()
        record.mark_success(result={'deleted_notifications': deleted})
        return {'deleted_notifications': deleted}
    except Exception as exc:
        record.mark_failed(error=str(exc))
        logger.exception('Cleanup expired notifications failed')
        raise
