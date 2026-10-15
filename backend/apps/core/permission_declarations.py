"""始终保留的核心权限；可选业务权限由各模块 manifest 声明。"""
PERMISSIONS = [
    ('user', 'read', '查看用户', 'user:read'),
    ('user', 'sensitive_read', '查看用户联系方式原值（需密码确认）', 'user:sensitive_read'),
    ('user', 'create', '创建用户', 'user:create'),
    ('user', 'update', '修改用户', 'user:update'),
    ('user', 'delete', '删除用户', 'user:delete'),
    ('role', 'read', '查看角色', 'role:read'),
    ('role', 'update', '修改角色', 'role:update'),
    ('log', 'read', '查看日志', 'log:read'),
    ('menu', 'read', '查看菜单配置', 'menu:read'),
    ('menu', 'update', '维护菜单配置', 'menu:update'),
    ('session', 'read', '查看在线用户', 'session:read'),
    ('session', 'revoke', '撤销用户登录会话', 'session:revoke'),
]
