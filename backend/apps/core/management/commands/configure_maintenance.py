"""只在缺失时录入维护计划，保留管理员调整的时间与启停状态。"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from apps.core.modules import task_enabled


class Command(BaseCommand):
    help = '幂等录入维护计划，不立即执行清理'

    @transaction.atomic
    def handle(self, *args, **options):
        for name, task, minute in [
            ('AdminCore 每日数据库与媒体备份', 'tasks.request_backup', '0'),
            ('AdminCore 每日软删除文件清理', 'tasks.cleanup_soft_deleted_files', '0'),
            ('AdminCore 每日已读通知清理', 'tasks.cleanup_expired_notifications', '15'),
            ('AdminCore 可靠事件派发', 'core.dispatch_outbox', '*'),
            ('AdminCore 幂等记录清理', 'core.cleanup_expired_idempotency', '30'),
            ('AdminCore 失效设备会话清理', 'core.cleanup_expired_sessions', '45'),
        ]:
            if not task_enabled(task):
                self.stdout.write(f'模块未启用，跳过维护计划：{name}')
                continue
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=minute, hour='*' if minute == '*' else ('2' if task == 'tasks.request_backup' else '3'),
                day_of_week='*', day_of_month='*', month_of_year='*',
                timezone=settings.TIME_ZONE,
            )
            entry, created = PeriodicTask.objects.get_or_create(
                name=name, defaults={'task': task, 'crontab': schedule, 'enabled': task != 'tasks.request_backup'},
            )
            self.stdout.write(f'{"创建" if created else "保留"}维护计划：{entry.name}')
