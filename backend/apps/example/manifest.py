"""示例业务的唯一声明入口；没有 ORM 或可执行环境配置。"""
from apps.core.contracts import Module, MenuDeclaration, Parameter

MODULE = Module('example', '示例工单', 'example', 'apps.example.urls', ('/example',),
    default_enabled=False,
    permissions=(('example', 'read', '查看示例工单', 'example:read'),
                 ('example', 'create', '创建示例工单', 'example:create'),
                 ('example', 'update', '修改示例工单', 'example:update'),
                 ('example', 'delete', '删除示例工单', 'example:delete')),
    menus=(MenuDeclaration('示例工单', '/example', 'clipboard-check', 'example:read', 100),),
    parameters=(Parameter('example.title_limit', '示例工单标题最大长度', 'integer', 120, 20, 120),),
    data_resources=(('example', '示例工单'),),
    audit_fields=(('example', ('id', 'status', 'priority', 'creator_id', 'version', 'title_sha256')),))
