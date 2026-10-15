from apps.core.contracts import MenuDeclaration, Module

MODULE = Module('sso', '企业身份登录', 'sso', 'apps.sso.urls',
    ('/integrations/identities', '/enterprise-login'), default_enabled=False,
    permissions=(('sso', 'read', '查看企业身份绑定', 'sso:read'),
                 ('sso', 'bind', '绑定企业身份', 'sso:bind'),
                 ('sso', 'unbind', '撤销企业身份绑定', 'sso:unbind')),
    menus=(MenuDeclaration('企业身份绑定', '/integrations/identities', 'building-2', 'sso:read', 96),),
    audit_fields=(('sso_identity', ('id', 'user_id', 'issuer', 'revoked_at', 'binding_version')),))
