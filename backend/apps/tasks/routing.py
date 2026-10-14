"""Celery 发布时登记白名单超时；不更改宿主备份和核心调度策略。"""
from celery import Task


class RegisteredPolicyTask(Task):
    abstract = True

    def apply_async(self, args=None, kwargs=None, **options):
        limits = registered_policy(self.name, args, kwargs, options)
        if limits:
            # 显式请求快照优先；定时任务在真正发布时读取当前配置。
            for key, value in limits.items():
                options.setdefault(key, value)
        return super().apply_async(args=args, kwargs=kwargs, **options)


def registered_policy(name, args, kwargs, options, task=None, **extra):
    if name not in {'data_io.run_data_import', 'tasks.run_maintenance', 'tasks.cleanup_lifecycle',
                    'tasks.cleanup_soft_deleted_files', 'tasks.cleanup_expired_notifications'}:
        return None
    from .reliability import policy
    current = policy('import' if name == 'data_io.run_data_import' else 'maintenance')
    return {'soft_time_limit': current['soft_timeout'], 'time_limit': current['hard_timeout']}


def record_scheduled_policy(record, key, options, celery_request):
    from .models import MaintenanceRequest
    from .reliability import policy
    current = policy('maintenance')
    limits = getattr(celery_request, 'timelimit', None)
    if limits and len(limits) == 2 and all(type(value) is int for value in limits):
        current['hard_timeout'], current['soft_timeout'] = limits
    MaintenanceRequest.objects.get_or_create(record=record, defaults={
        'key': key, 'options': options, 'session_version': 0, 'policy': current})
