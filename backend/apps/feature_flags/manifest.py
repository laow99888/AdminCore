from apps.core.contracts import Module, MenuDeclaration


MODULE = Module('feature_flags', '特性开关', 'feature-flags', 'apps.feature_flags.urls',
    ('/system/feature-flags',), default_enabled=False,
    permissions=(('feature_flag', 'read', '查看特性开关', 'feature_flag:read'),
                 ('feature_flag', 'create', '创建特性开关', 'feature_flag:create'),
                 ('feature_flag', 'update', '修改特性开关', 'feature_flag:update'),
                 ('feature_flag', 'delete', '删除特性开关', 'feature_flag:delete')),
    menus=(MenuDeclaration('特性开关', '/system/feature-flags', 'settings', 'feature_flag:read', 25),),
    audit_fields=(('feature_flag', ('id', 'key', 'enabled', 'rollout', 'included_users',
                                 'excluded_users', 'roles', 'version')),))
