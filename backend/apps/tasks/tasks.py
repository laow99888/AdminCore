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
def cleanup_soft_deleted_files(self):
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
    try:
        from apps.core.system_config import config_value
        retention_days = config_value('files.retention_days')
        cutoff = timezone.now() - timedelta(days=retention_days)
        expired = list(FileModel.objects.filter(is_deleted=True, deleted_at__lt=cutoff))
        for file_obj in expired:
            file_obj.hard_delete()

        record.mark_success(result={'purged_files': len(expired), 'retention_days': retention_days})
        logger.info('Cleanup purged %d expired files', len(expired))
        return {'purged_files': len(expired)}
    except Exception as exc:
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
