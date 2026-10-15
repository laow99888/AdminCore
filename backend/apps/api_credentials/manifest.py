from apps.core.contracts import MenuDeclaration, Module

MODULE = Module('api_credentials', '只读开放 API', 'api-credentials', 'apps.api_credentials.urls',
    ('/integrations/credentials',), default_enabled=False,
    permissions=(('api_credential', 'read', '查看本人开放凭证', 'api_credential:read'),
                 ('api_credential', 'create', '创建本人开放凭证', 'api_credential:create'),
                 ('api_credential', 'revoke', '撤销本人开放凭证', 'api_credential:revoke')),
    menus=(MenuDeclaration('开放凭证', '/integrations/credentials', 'key-round', 'api_credential:read', 95),),
    audit_fields=(('api_credential', ('id', 'scopes', 'expires_at', 'revoked_at', 'owner_id')),))
