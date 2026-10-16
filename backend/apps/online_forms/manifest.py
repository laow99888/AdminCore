from apps.core.contracts import Module, MenuDeclaration


MODULE = Module(
    'online_forms', '在线表单', 'online-forms', 'apps.online_forms.urls', ('/online-forms',),
    default_enabled=False,
    permissions=(
        ('online_form', 'read', '查看在线表单', 'online_form:read'),
        ('online_form', 'create', '创建在线表单', 'online_form:create'),
        ('online_form', 'update', '修改在线表单', 'online_form:update'),
        ('online_form', 'publish', '发布在线表单', 'online_form:publish'),
        ('online_form', 'record_read', '查看表单记录', 'online_form:record_read'),
        ('online_form', 'record_create', '提交表单记录', 'online_form:record_create'),
        ('online_form', 'record_update', '修改表单记录', 'online_form:record_update'),
    ),
    menus=(MenuDeclaration('在线表单', '/online-forms', 'edit', 'online_form:read', 35),),
    data_resources=(('online_form', '在线表单'), ('online_record', '在线表单记录')),
    audit_fields=(('online_form', ('id', 'code', 'status', 'version', 'created_by_id', 'published_by_id')),
                  ('online_record', ('id', 'form_id', 'form_version', 'owner_id', 'version'))),
)
