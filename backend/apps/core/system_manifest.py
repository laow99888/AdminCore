"""内置模块唯一静态声明；不导入模型或访问数据库。"""
from apps.core.contracts import Module, MenuDeclaration

MODULE = Module('system', '系统管理', 'system', 'apps.core.system_urls', ('/system/config', '/system/dictionaries', '/system/information', '/system/monitor', '/system/cache', '/system/codegen'),
    permissions=(
        ('codegen', 'generate', '配置和下载业务源码', 'codegen:generate'),
        ('diagnostics', 'read', '查看系统信息', 'diagnostics:read'),
        ('monitor', 'read', '查看服务监控', 'monitor:read'),
        ('cache', 'read', '查看业务缓存目录', 'cache:read'),
        ('cache', 'clear', '清理登记的业务缓存', 'cache:clear'),
        ('config', 'read', '查看系统参数', 'config:read'),
        ('config', 'update', '修改系统参数', 'config:update'),
        ('dictionary', 'read', '查看数据字典', 'dictionary:read'),
        ('dictionary', 'update', '维护数据字典', 'dictionary:update'),
    ),
    audit_fields=(
        ('system_config', ('value',)),
        ('dictionary', ('id', 'code', 'name', 'is_active', 'version', 'items_count')),
    ),
    menus=(
        MenuDeclaration('代码生成器', '/system/codegen', 'code-xml', 'codegen:generate', 21),
        MenuDeclaration('系统参数', '/system/config', 'settings', 'config:read', 11),
        MenuDeclaration('数据字典', '/system/dictionaries', 'list-tree', 'dictionary:read', 12),
        MenuDeclaration('系统信息', '/system/information', 'info', 'diagnostics:read', 17),
        MenuDeclaration('服务监控', '/system/monitor', 'activity', 'monitor:read', 18),
        MenuDeclaration('缓存管理', '/system/cache', 'database', 'cache:read', 20),
    ))
