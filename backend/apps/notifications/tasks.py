"""定时发布已到期的业务通知摘要，重复投递由用户锁和待处理状态去重。"""
from celery import shared_task

from apps.core.modules import require_task
from .digests import refresh_due


@shared_task(name='notifications.refresh_digests', soft_time_limit=50, time_limit=60)
def refresh_digests(limit=100):
    require_task('notifications.refresh_digests')
    return refresh_due(limit=limit, all_tenants=True)
