from apps.core.contracts import Module, MenuDeclaration


MODULE = Module('ip_policy', 'IP 访问策略', 'ip-policy', 'apps.ip_policy.urls',
    ('/system/ip-policy',), default_enabled=False,
    permissions=(('ip_policy', 'read', '查看 IP 策略', 'ip_policy:read'),
                 ('ip_policy', 'update', '修改 IP 策略', 'ip_policy:update')),
    menus=(MenuDeclaration('IP 访问策略', '/system/ip-policy', 'settings', 'ip_policy:read', 26),),
    audit_fields=(('ip_policy', ('enabled', 'allow', 'deny', 'version')),))
