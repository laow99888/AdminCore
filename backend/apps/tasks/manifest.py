"""内置模块唯一静态声明；不导入模型或访问数据库。"""
from apps.core.contracts import Module, MenuDeclaration, Parameter

MODULE = Module('tasks', '任务中心', 'tasks', 'apps.tasks.urls', ('/tasks',),
    tasks=('tasks.cleanup_lifecycle', 'tasks.request_backup', 'tasks.run_maintenance',
           'tasks.cleanup_soft_deleted_files', 'tasks.cleanup_expired_notifications'),
    task_requires=(('tasks.cleanup_soft_deleted_files', ('files',)),
                   ('tasks.cleanup_expired_notifications', ('notifications',))),
    data_resources=(('task', '任务'),),
    permissions=(
        ('task', 'read', '查看任务', 'task:read'),
        ('task', 'cancel', '取消任务', 'task:cancel'),
        ('task', 'retry', '接续失败导入任务', 'task:retry'),
        ('task', 'delete', '清理任务历史', 'task:delete'),
        ('schedule', 'read', '查看维护计划', 'schedule:read'),
        ('schedule', 'update', '修改维护计划', 'schedule:update'),
        ('schedule', 'run', '手动执行维护任务', 'schedule:run'),
    ),
    audit_fields=(
        ('task', ('id', 'task_type', 'status', 'progress', 'creator_id', 'celery_task_id')),
        ('maintenance_schedule', ('task', 'enabled', 'cron', 'kwargs')),
        ('maintenance_run', ('key', 'options', 'preview_id', 'status')),
    ),
    menus=(
        MenuDeclaration('任务中心', '/tasks', 'list-checks', 'task:read', 8),
        MenuDeclaration('定时维护', '/tasks/schedules', 'clock', 'schedule:read', 16),
    ),
    parameters=(
        Parameter(key='tasks.import_timeout', label='导入软超时秒数（新任务）', kind='integer', default=300, minimum=30, maximum=1800),
        Parameter(key='tasks.maintenance_timeout', label='维护软超时秒数（新任务）', kind='integer', default=270, minimum=30, maximum=900),
        Parameter(key='tasks.dispatch_attempts', label='可靠入队最多尝试次数（新任务）', kind='integer', default=5, minimum=1, maximum=10),
        Parameter(key='tasks.failure_alert', label='任务失败站内告警（0关闭/1开启）', kind='integer', default=1, minimum=0, maximum=1),
        Parameter(key='tasks.failure_email', label='任务失败邮件告警（0关闭/1开启）', kind='integer', default=0, minimum=0, maximum=1),
    ))
