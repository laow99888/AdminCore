"""始终保留的核心菜单；可选业务菜单由模块 manifest 声明。"""
MENUS = [
    ('仪表盘', '/', 'layout-dashboard', 1, None, None),
    ('用户管理', '/users', 'users', 2, None, 'user:read'),
    ('角色权限', '/roles', 'shield-check', 3, None, 'role:read'),
    ('菜单管理', '/menus', 'list-tree', 4, None, 'menu:read'),
    ('操作日志', '/logs', 'file-text', 9, None, 'log:read'),
    ('系统设置', '/settings', 'settings', 10, None, None),
    ('可靠事件', '/reliability/events', 'list-checks', 14, None, None),
    ('在线用户', '/system/online-users', 'users', 22, None, 'session:read'),
]
