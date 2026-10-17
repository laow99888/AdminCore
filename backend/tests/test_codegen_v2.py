"""V2 协议、源码预览下载和手写扩展保护。真实安装另有独立验收脚本。"""
import ast
from copy import deepcopy
from io import BytesIO
import json
import zipfile
import pytest
from apps.core.codegen.spec import parse_definition, GenerationError
from apps.core.codegen.render import render
from apps.core.codegen import plans


def definition():
    return {'schema_version': 2, 'module': 'purchase_orders', 'model': 'PurchaseOrder', 'title': '采购订单',
            'structure': 'master_detail', 'fields': [
                {'name': 'code', 'label': '订单编码', 'kind': 'string', 'unique': True, 'query': 'contains', 'sortable': True},
                {'name': 'amount', 'label': '金额', 'kind': 'decimal', 'minimum': '0', 'query': 'range'},
                {'name': 'due_date', 'label': '日期', 'kind': 'date', 'required': False},
                {'name': 'placed_at', 'label': '时间', 'kind': 'datetime', 'required': False},
                {'name': 'status', 'label': '状态', 'kind': 'enum', 'choices': [{'value': 'draft', 'label': '草稿'}]},
                {'name': 'supplier', 'label': '供应商', 'kind': 'relation', 'required': False, 'target': {'module': 'suppliers', 'model': 'Supplier', 'label': 'name'}},
                {'name': 'attachment', 'label': '附件', 'kind': 'file', 'required': False},
                {'name': 'category', 'label': '分类', 'kind': 'dictionary', 'dictionary': 'purchase_category', 'required': False}],
            'details': [{'name': 'lines', 'label': '采购明细', 'model': 'PurchaseLine', 'min_rows': 1,
                         'fields': [{'name': 'name', 'label': '名称', 'kind': 'string'},
                                    {'name': 'quantity', 'label': '数量', 'kind': 'integer', 'minimum': 1},
                                    {'name': 'price', 'label': '单价', 'kind': 'decimal', 'minimum': '0'}]}]}


def test_approval_and_report_generated_contract_is_explicit():
    raw = definition()
    raw['approval'] = {'flow_code': 'purchase-flow', 'title_field': 'code'}
    raw['reports'] = {'dimensions': ['approval_status'], 'metrics': ['amount'], 'filters': ['amount']}
    spec = parse_definition(raw); files = render(spec)
    assert spec.as_dict()['approval'] == raw['approval']
    assert "dependencies=('approvals',)" in files['backend/apps/purchase_orders/manifest.py']
    assert 'approval_status = models.CharField' in files['backend/apps/purchase_orders/models.py']
    assert 'approval_request' in files['backend/apps/purchase_orders/serializers.py']
    assert "'submit': 'purchase_orders:submit'" in files['backend/apps/purchase_orders/views.py']
    for bad in [dict(raw, approval={'flow_code': 'x', 'title_field': 'amount'}),
                dict(raw, reports={'dimensions': ['supplier__name'], 'metrics': [], 'filters': []}),
                dict(raw, reports={'dimensions': [], 'metrics': ['supplier'], 'filters': []})]:
        with pytest.raises(GenerationError): parse_definition(bad)


def test_v2_deterministic_real_source():
    parsed = parse_definition(definition())
    files = render(parsed)
    assert files == render(parse_definition(parsed.as_dict()))
    for path, content in files.items():
        if path.endswith('.py'):
            ast.parse(content)
    assert "models.DecimalField(max_digits=18, decimal_places=2" in files['backend/apps/purchase_orders/models.py']
    assert "related_name='lines'" in files['backend/apps/purchase_orders/models.py']
    assert 'GeneratedViewMixin' in files['backend/apps/purchase_orders/views.py']
    assert 'GeneratedCrudPage' in files['frontend/src/views/purchase_orders/GeneratedPage.vue']


@pytest.mark.parametrize('change', [
    {'schema_version': True}, {'structure': []}, {'table': 'existing_business'}, {'details': []},
    {'ordering': ['supplier__password']}, {'ordering': ['code', '-code']},
    {'model': 'Decimal'}, {'model': 'BaseModel'}, {'model': 'GeneratedService'},
    {'fields': [{'name': 'tenant_id', 'label': '租户', 'kind': 'string'}]},
    {'fields': [{'name': 'value', 'label': '金额', 'kind': 'decimal', 'default': 0.1}]},
    {'fields': [{'name': 'value', 'label': '金额', 'kind': 'decimal', 'default': '1.001'}]},
    {'fields': [{'name': 'value', 'label': '金额', 'kind': 'decimal', 'default': 'NaN'}]},
    {'fields': [{'name': 'value', 'label': '金额', 'kind': 'decimal', 'default': '99999999999999999.99'}]},
    {'fields': [{'name': 'value', 'label': '日期', 'kind': 'date', 'default': '2026-02-30'}]},
    {'fields': [{'name': 'value', 'label': '时间', 'kind': 'datetime', 'default': '2026-10-18T12:00:00'}]},
    {'fields': [{'name': 'value', 'label': '字段', 'kind': 'string', 'component': 'my-script'}]},
    {'fields': [{'name': 'value', 'label': '字段', 'kind': 'string', 'query': []}]},
    {'fields': [{'name': 'value', 'label': '字段', 'kind': 'string', 'script': 'alert(1)'}]},
    {'fields': [{'name': 'value', 'label': '字段', 'kind': 'relation', 'target': {'module': 'auth_app', 'model': 'User', 'label': 'username'}}]},
])
def test_v2_invalid_definitions(change):
    with pytest.raises(GenerationError):
        parse_definition({**definition(), **change})


def test_v2_tree_and_detail_identifier_collisions():
    raw = definition(); raw.update(structure='tree', details=[])
    assert "models.ForeignKey('self', on_delete=models.PROTECT" in render(parse_definition(raw))['backend/apps/purchase_orders/models.py']
    raw = definition(); raw['details'][0]['name'] = 'code'
    with pytest.raises(GenerationError):
        parse_definition(raw)


def test_v2_implicit_names_and_casefolded_models_cannot_collide():
    raw = definition(); raw['details'][0]['name'] = 'supplier_id'
    with pytest.raises(GenerationError):
        parse_definition(raw)
    raw = definition(); raw['details'][0]['model'] = 'Purchaseorder'
    with pytest.raises(GenerationError):
        parse_definition(raw)
    raw = definition(); raw['fields'].append({'name': 'amount_min', 'label': '字段', 'kind': 'string', 'query': 'eq'})
    with pytest.raises(GenerationError):
        parse_definition(raw)
    raw = definition(); raw['fields'][0]['name'] = 'objects'
    with pytest.raises(GenerationError):
        parse_definition(raw)
    raw = definition(); raw['details'][0]['model'] = 'PurchaseOrderStatusChoice'
    with pytest.raises(GenerationError):
        parse_definition(raw)


def test_extensions_survive_regeneration(tmp_path):
    raw = definition(); files = render(parse_definition(raw))
    initial = plans.make_plan(tmp_path, raw, files)
    plans.apply_plan(tmp_path, initial, raw, files, list(files))
    paths = ['backend/apps/purchase_orders/extensions.py', 'frontend/src/views/purchase_orders/RecordListView.vue']
    for path in paths:
        (tmp_path / path).write_text('# hand-written business rule', encoding='utf-8')
    updated = deepcopy(raw); updated['fields'][0]['label'] = '采购编号'
    next_files = render(parse_definition(updated)); next_plan = plans.make_plan(tmp_path, updated, next_files)
    assert all(row['state'] == 'preserved' for row in next_plan['entries'] if row['path'] in paths)
    with pytest.raises(GenerationError, match='只允许首次创建'):
        plans.apply_plan(tmp_path, next_plan, updated, next_files, [paths[0]])
    plans.apply_plan(tmp_path, next_plan, updated, next_files, [name for name in next_files if name not in paths])
    assert all((tmp_path / path).read_text(encoding='utf-8') == '# hand-written business rule' for path in paths)


def test_v1_cannot_accidentally_replace_v2_handwritten_entry(tmp_path):
    raw = definition(); files = render(parse_definition(raw))
    plans.apply_plan(tmp_path, plans.make_plan(tmp_path, raw, files), raw, files, list(files))
    old = {'module': raw['module'], 'model': raw['model'], 'title': raw['title'],
           'fields': [{'name': 'code', 'label': '编码', 'kind': 'string'}]}
    with pytest.raises(GenerationError, match='V2'):
        plans.make_plan(tmp_path, old, render(parse_definition(old)))
    with pytest.raises(GenerationError, match='V2'):
        plans.apply_plan(tmp_path, {}, old, render(parse_definition(old)), ['backend/apps/purchase_orders/__init__.py'])


@pytest.mark.django_db
def test_codegen_preview_and_zip_are_identical_and_private(admin_client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = admin_client.post('/api/v1/system/codegen/preview/', {'definition': definition()}, format='json')
    assert response.status_code == 200, response.content
    files = response.json()['files']
    assert response['Cache-Control'] == 'private, no-store'
    response = admin_client.post('/api/v1/system/codegen/download/', {'definition': definition()}, format='json')
    assert response.status_code == 200
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert all(archive.read(row['path']).decode() == row['content'] for row in files)
        assert json.loads(archive.read('codegen-definition.json'))['schema_version'] == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.django_db
def test_codegen_requires_admin_and_explicit_permission(member_client, member_user):
    from apps.permissions.models import Role, Permission, RolePermission, UserRole
    role = Role.objects.create(name='generator-developer')
    permission = Permission.objects.create(name='generate', resource='codegen', action='generate', code='codegen:generate')
    RolePermission.objects.create(role=role, permission=permission); UserRole.objects.create(user=member_user, role=role)
    assert member_client.post('/api/v1/system/codegen/preview/', {'definition': definition()}, format='json').status_code == 403


@pytest.mark.django_db
def test_codegen_invalid_definition_is_controlled_error(admin_client):
    for value in [[], {}, {'schema_version': 2, 'module': '../escape'}, {**definition(), 'fields': 'not-array'}]:
        response = admin_client.post('/api/v1/system/codegen/preview/', {'definition': value}, format='json')
        assert response.status_code == 400
