from apps.core.contracts import Module, MenuDeclaration


MODULE = Module(
    'reports', '报表与大屏', 'reports', 'apps.reports.urls', ('/reports',),
    default_enabled=False,
    permissions=(
        ('report', 'read', '查看报表', 'report:read'),
        ('report', 'create', '创建报表', 'report:create'),
        ('report', 'update', '修改报表', 'report:update'),
        ('report', 'publish', '发布报表', 'report:publish'),
        ('report', 'execute', '运行报表', 'report:execute'),
    ),
    menus=(MenuDeclaration('报表与大屏', '/reports', 'data-analysis', 'report:read', 38),),
    data_resources=(('report', '报表定义'),),
    audit_fields=(('report', ('id', 'code', 'kind', 'status', 'version', 'created_by_id', 'published_by_id')),),
)
