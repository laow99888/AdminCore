"""通过模块契约和真实 API 验证示例业务；SQL 竞争另在隔离 PostgreSQL。"""
from dataclasses import replace
from unittest.mock import patch
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from apps.core.contracts import validate_registry, Parameter, MenuDeclaration
from apps.core.modules import MODULES, PRESETS
from apps.core.models import DataScopeGrant, Department, OrganizationMembership, SystemConfig
from apps.example.models import WorkItem
from apps.example.manifest import MODULE
from apps.logs.models import OperationLog
from apps.permissions.models import Role, Permission, RolePermission, UserRole, Menu

pytestmark = pytest.mark.django_db
URL = '/api/v1/example/items/'


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'example')
    settings.ROOT_URLCONF = 'tests.example_urls'


def grant(user, codes=None):
    role = Role.objects.create(name='example-role-' + str(user.pk))
    for resource, action, name, code in MODULE.permissions:
        permission, _ = Permission.objects.get_or_create(resource=resource, action=action, defaults={'name': name, 'code': code})
        if codes is None or code in codes:
            RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=user, role=role)
    return role


def create(client, **extra):
    return client.post(URL, {'title': '工单标题', 'notes': '私有正文', 'version': 0, **extra}, format='json')


def test_example_defaults_off_and_manifest_contract(admin_client, settings):
    assert 'example' not in PRESETS['minimal'] and 'example' not in PRESETS['standard']
    validate_registry(MODULES)
    data = admin_client.get('/api/v1/modules/').json()['data']
    example = next(row for row in data['modules'] if row['key'] == 'example')
    assert example['page_permissions'] == {'/example': 'example:read'}
    assert {'key': 'example', 'title': '示例工单'} in data['scope_resources']
    assert 'example.title_limit' in {row['key'] for row in admin_client.get('/api/v1/system/config/').json()['data']}
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'example')
    assert admin_client.get(URL).status_code == 404 and create(admin_client).status_code == 404
    assert admin_client.get('/api/v1/system/config/example.title_limit/').status_code == 404


def test_crud_versions_whitelist_and_private_audit(admin_client):
    response = create(admin_client)
    assert response.status_code == 201
    row = response.json()['data']
    assert row['version'] == 1 and row['status'] == 'open'
    detail = URL + row['id'] + '/'
    assert admin_client.get(detail)['Cache-Control'] == 'private, no-store'
    assert admin_client.patch(detail, {'status': 'done'}, format='json').status_code == 400
    assert admin_client.patch(detail, {'status': 'done', 'version': 0}, format='json').status_code == 409
    assert admin_client.patch(detail, {'status': 'done', 'version': 1}, format='json').status_code == 200
    audit = OperationLog.objects.get(resource='example', action='update')
    assert audit.before_values['status'] == 'open' and audit.after_values['status'] == 'done'
    assert '工单标题' not in str(audit.after_values) and '私有正文' not in str(audit.after_values)
    assert admin_client.delete(detail, {'version': 1}, format='json').status_code == 409
    assert admin_client.delete(detail, {'version': 2}, format='json').status_code == 200
    assert admin_client.get(detail).status_code == 404


@pytest.mark.parametrize('extra', [{'creator': '00000000-0000-0000-0000-000000000001'},
    {'status': 'unknown'}, {'priority': 'unknown'}, {'title': ''}, {'title': 'x' * 121}, {'notes': 'x' * 2001}, {'is_staff': True}])
def test_invalid_or_owner_mass_assignment_rejected(admin_client, extra):
    assert create(admin_client, **extra).status_code == 400
    assert not WorkItem.objects.exists() and not OperationLog.objects.filter(resource='example').exists()


def test_member_permission_matrix_and_owner_scope(member_client, member_user, admin_user):
    assert member_client.get(URL).status_code == 403
    role = grant(member_user, ['example:read'])
    mine = WorkItem.objects.create(title='mine', creator=member_user)
    other = WorkItem.objects.create(title='other', creator=admin_user)
    assert [row['id'] for row in member_client.get(URL).json()['data']['items']] == [str(mine.pk)]
    assert member_client.get(URL + str(other.pk) + '/').status_code == 404
    assert create(member_client).status_code == 403
    assert member_client.patch(URL + str(mine.pk) + '/', {'version': 1, 'title': 'new'}, format='json').status_code == 403
    for permission in Permission.objects.filter(code__in=['example:create', 'example:update', 'example:delete']):
        RolePermission.objects.create(role=role, permission=permission)
    assert create(member_client).status_code == 201
    assert member_client.patch(URL + str(other.pk) + '/', {'version': 1, 'title': 'new'}, format='json').status_code == 404
    assert member_client.delete(URL + str(other.pk) + '/', {'version': 1}, format='json').status_code == 404


def test_department_scope_survives_organization_disabled(member_client, member_user, admin_user, settings):
    role = grant(member_user)
    department = Department.objects.create(name='A')
    OrganizationMembership.objects.create(user=member_user, department=department)
    OrganizationMembership.objects.create(user=admin_user, department=department)
    rule = DataScopeGrant.objects.create(role=role, resource='example', scope='department')
    other = WorkItem.objects.create(title='department-visible', creator=admin_user)
    assert member_client.get(URL + str(other.pk) + '/').status_code == 200
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'organization')
    assert member_client.get(URL + str(other.pk) + '/').status_code == 200
    rule.scope = 'self'; rule.save()
    assert member_client.get(URL + str(other.pk) + '/').status_code == 404


def test_new_parameter_and_disabled_data_preserved(admin_client, admin_user, settings):
    key = '/api/v1/system/config/example.title_limit/'
    assert admin_client.patch(key, {'value': 20, 'version': 0}, format='json').status_code == 200
    assert create(admin_client, title='x' * 21).status_code == 400
    row = create(admin_client).json()['data']
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'example')
    assert admin_client.patch(key, {'value': 120, 'version': 1}, format='json').status_code == 404
    assert WorkItem.objects.filter(pk=row['id']).exists() and SystemConfig.objects.get(key='example.title_limit').value == 20
    settings.ADMINCORE_MODULES += ('example',)
    assert admin_client.get(URL + row['id'] + '/').status_code == 200


def test_create_idempotency_replays_once_but_rechecks_scope(member_client, member_user):
    role = grant(member_user)
    client = member_client
    payload = {'title': 'once', 'version': 0}
    first = client.post(URL, payload, format='json', HTTP_IDEMPOTENCY_KEY='example-once')
    second = client.post(URL, payload, format='json', HTTP_IDEMPOTENCY_KEY='example-once')
    assert first.status_code == 201 and second.status_code == 201 and first.json() == second.json()
    assert second['Idempotency-Replayed'] == 'true'
    assert WorkItem.objects.count() == 1 and OperationLog.objects.filter(resource='example').count() == 1
    DataScopeGrant.objects.create(role=role, resource='example', scope='custom')
    assert client.post(URL, payload, format='json', HTTP_IDEMPOTENCY_KEY='example-once').status_code == 404


def test_audit_failure_rolls_back_business_write(admin_client):
    with patch('apps.example.services.write_audit', side_effect=RuntimeError('fixture')):
        assert create(admin_client).status_code == 500
    assert not WorkItem.objects.exists()


@pytest.mark.parametrize('bulk', [False, True])
def test_creator_reference_rejects_user_deletion_atomically(admin_client, admin_user, member_user, bulk):
    item = WorkItem.objects.create(title='保留引用', creator=member_user)
    if bulk:
        response = admin_client.post('/api/v1/users/bulk_action/',
            {'user_ids': [str(member_user.pk)], 'action': 'delete'}, format='json')
    else:
        response = admin_client.delete('/api/v1/users/' + str(member_user.pk) + '/')
    assert response.status_code == 409
    assert type(member_user).objects.filter(pk=member_user.pk).exists()
    assert WorkItem.objects.filter(pk=item.pk).exists()
    assert not OperationLog.objects.filter(resource='user', action='delete').exists()
    assert str(item.pk) not in str(response.data)


@pytest.mark.parametrize('module', [replace(MODULE, key='Bad!'), replace(MODULE, dependencies=('absent',)),
    replace(MODULE, dependencies=('example',)), replace(MODULE, menus=(MenuDeclaration('bad', '/users', 'users', 'example:read'),)),
    replace(MODULE, parameters=(Parameter('other.value', 'bad', 'integer', 3),)),
    replace(MODULE, parameters=(Parameter('example.bad', 'bad', 'integer', True),)),
    replace(MODULE, data_resources=(('user', '冲突'),)),
    replace(MODULE, api_prefix='users'),
    replace(MODULE, paths=('/users',), menus=(MenuDeclaration('bad', '/users', 'users', 'example:read'),)),
    replace(MODULE, paths=('/settings/private',), menus=()),
    replace(MODULE, permissions=(('example', 'read*', 'bad', 'example:read*'),), menus=()),
    replace(MODULE, permissions=(('user', 'read', '冲突', 'user:read'),))])
def test_invalid_extension_declarations_rejected(module):
    with pytest.raises(ImproperlyConfigured):
        validate_registry((module,))


def test_seed_extension_menu_once_and_preserve_existing_role_permissions(admin_user, monkeypatch):
    from io import StringIO
    admin_user.set_password('BootstrapFixture#987654321'); admin_user.save()
    role = Role.objects.create(name='系统管理员')
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not RolePermission.objects.filter(role=role, permission__code__startswith='example:').exists()
    menu = Menu.objects.get(path='/example')
    menu.delete()
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not Menu.objects.filter(path='/example').exists()
