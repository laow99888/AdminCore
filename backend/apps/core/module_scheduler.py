"""关闭模块不改管理员计划状态；重新启用后沿用原计划。"""
from django_celery_beat.schedulers import DatabaseScheduler
from .modules import MAINTENANCE_TASKS, MODULES, task_enabled


class ModuleScheduler(DatabaseScheduler):
    def enabled_models_qs(self):
        registered = set(MAINTENANCE_TASKS) | {task for module in MODULES for task in module.tasks}
        return super().enabled_models_qs().filter(task__in=[name for name in registered if task_enabled(name)])
