"""内置模块唯一静态声明；不导入模型或访问数据库。"""
from apps.core.contracts import Module, MenuDeclaration

MODULE = Module('organization', '组织与数据权限', 'organization', 'apps.core.organization_urls', ('/organization',),
    permissions=(
        ('post', 'read', '查看岗位与任职', 'post:read'),
        ('post', 'update', '维护岗位与任职', 'post:update'),
    ),
    audit_fields=(
        ('department', ('id', 'name', 'parent', 'order', 'is_active', 'version', 'leader')),
        ('appointment', ('id', 'user', 'department', 'kind', 'starts_on', 'ends_on', 'cancelled', 'reason', 'version')),
        ('membership', ('id', 'user', 'department', 'version')),
        ('data_scope', ('id', 'role', 'resource', 'scope', 'departments', 'version')),
        ('post', ('id', 'code', 'name', 'order', 'is_active', 'version')),
        ('user_post', ('id', 'user', 'post', 'version')),
    ),
    menus=(
        MenuDeclaration('组织与数据权限', '/organization', 'users', None, 13),
        MenuDeclaration('岗位与任职', '/organization/posts', 'briefcase-business', 'post:read', 19),
    ))
