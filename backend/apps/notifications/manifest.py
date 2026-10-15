"""内置模块唯一静态声明；不导入模型或访问数据库。"""
from apps.core.contracts import Module, MenuDeclaration, Parameter

MODULE = Module('notifications', '通知中心', 'notifications', 'apps.notifications.urls', ('/notifications',),
    permissions=(
        ('announcement', 'read', '查看公告管理', 'announcement:read'),
        ('announcement', 'update', '维护公告草稿', 'announcement:update'),
        ('announcement', 'publish', '发布和撤回公告', 'announcement:publish'),
        ('template', 'read', '查看通知模板与投递', 'template:read'),
        ('template', 'update', '维护通知模板版本', 'template:update'),
        ('template', 'send', '发送模板通知与重试', 'template:send'),
    ),
    audit_fields=(
        ('message_template', ('id', 'code', 'enabled', 'revision', 'variables', 'content_sha256')),
        ('message_delivery', ('id', 'template_id', 'revision', 'channels', 'count', 'status', 'attempts')),
        ('notification', ('id', 'recipient_id', 'notification_type', 'is_read', 'read_at', 'content_length', 'content_sha256')),
        ('announcement', ('id', 'version', 'status', 'content_format', 'content_length', 'content_sha256')),
    ),
    menus=(
        MenuDeclaration('通知中心', '/notifications', 'bell', None, 7),
        MenuDeclaration('通知公告', '/notifications/announcements', 'bell', None, 21),
        MenuDeclaration('通知模板', '/notifications/templates', 'mail', 'template:read', 23),
    ),
    parameters=(
        Parameter(key='notifications.retention_days', label='已读通知保留天数', kind='integer', default=90, setting='NOTIFICATION_RETENTION_DAYS', minimum=1, maximum=3650),
    ))
