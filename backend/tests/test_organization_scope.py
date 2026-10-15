from django.contrib.auth import get_user_model
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.core.models import Department, OrganizationMembership, DataScopeGrant
from apps.permissions.models import Role, UserRole, Permission, RolePermission
from tests.file_permissions import grant_files
from apps.files.models import FileModel
from apps.logs.models import OperationLog
from apps.tasks.models import TaskRecord
from rest_framework.test import APIClient
import pytest

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def scoped_users(member_user):
    root = Department.objects.create(name='总部')
    child = Department.objects.create(name='团队', parent=root)
    outside = Department.objects.create(name='外部')
    team = User.objects.create_user('team_user')
    stranger = User.objects.create_user('outside_user')
    for user, department in [(member_user, root), (team, child), (stranger, outside)]:
        OrganizationMembership.objects.create(user=user, department=department)
    role = Role.objects.create(name='范围测试')
    UserRole.objects.create(user=member_user, role=role)
    for resource, action in [('user', 'read'), ('user', 'update'), ('user', 'delete'), ('user', 'create'),
                             ('log', 'read'), ('task', 'read'), ('task', 'cancel'), ('task', 'delete'),
                             ('data_io', 'export'), ('data_io', 'import')]:
        permission, _ = Permission.objects.get_or_create(resource=resource, action=action,
                                                        defaults={'name': resource + ':' + action, 'code': resource + ':' + action})
        RolePermission.objects.create(role=role, permission=permission)
    return root, child, outside, team, stranger, role


def test_department_crud_cycle_version_and_protected_delete(admin_client, member_client, member_user):
    base = '/api/v1/organization/departments/'
    assert member_client.get(base).status_code == 403
    parent = admin_client.post(base, {'name': '根部门', 'version': 0}, format='json').json()['data']
    child = admin_client.post(base, {'name': '子部门', 'parent': parent['id'], 'version': 0}, format='json').json()['data']
    assert admin_client.patch(base + parent['id'] + '/', {'parent': child['id'], 'version': 1}, format='json').status_code == 400
    assert admin_client.patch(base + parent['id'] + '/', {'name': '冲突', 'version': 0}, format='json').status_code == 409
    assert admin_client.patch(base + parent['id'] + '/', {'is_active': False, 'version': 1}, format='json').status_code == 400
    assert admin_client.delete(base + parent['id'] + '/').status_code == 400
    membership = admin_client.post('/api/v1/organization/memberships/', {'user': str(member_user.pk), 'department': child['id'], 'version': 0}, format='json')
    assert membership.status_code == 201
    membership_url = '/api/v1/organization/memberships/' + membership.json()['data']['id'] + '/'
    assert admin_client.patch(membership_url, {'department': parent['id'], 'version': 0}, format='json').status_code == 409
    assert admin_client.delete(base + child['id'] + '/').status_code == 400
    assert admin_client.patch(base + child['id'] + '/', {'is_active': False, 'version': 1}, format='json').status_code == 200


@pytest.mark.parametrize('scope,count', [('self', 1), ('department', 1), ('department_tree', 2), ('custom', 1), ('all', 3)])
def test_user_scope_list_detail_write_and_export(member_client, member_user, scoped_users, scope, count):
    root, child, outside, team, stranger, role = scoped_users
    grant = DataScopeGrant.objects.create(role=role, resource='user', scope=scope)
    if scope == 'custom':
        grant.departments.add(outside)
    response = member_client.get('/api/v1/users/')
    assert response.status_code == 200
    assert response.json()['data']['pagination']['total'] == count
    allowed_ids = {item['id'] for item in response.json()['data']['items']}
    for target in [member_user, team, stranger]:
        permitted = str(target.pk) in allowed_ids
        detail = '/api/v1/users/' + str(target.pk) + '/'
        assert member_client.get(detail).status_code == (200 if permitted else 404)
        if not permitted:
            assert member_client.delete(detail).status_code == 404
        target.refresh_from_db()
        assert member_client.patch(detail, {'first_name': '范围内', 'version': target.profile_version}, format='json').status_code == (200 if permitted else 404)
        # 本用例验证数据范围；显式不强制改密，避免自重置后中断后续范围断言。
        assert member_client.post(detail + 'reset_password/', {'password': 'ChangedSecure#7824', 'must_change_password': False}, format='json').status_code == (200 if permitted else 404)
        if target.pk == member_user.pk and permitted:
            login = member_client.post('/api/v1/auth/login/', {'username': member_user.username, 'password': 'ChangedSecure#7824'}, format='json')
            assert login.status_code == 200
            member_client.credentials(HTTP_AUTHORIZATION='Bearer ' + login.json()['access'])
    export = member_client.get('/api/v1/data-io/export/?resource=users')
    assert export.status_code == 200
    text = export.content.decode('utf-8-sig')
    for target in [member_user, team, stranger]:
        assert (target.username in text) == (str(target.pk) in allowed_ids)


def test_mixed_bulk_rejects_without_partial_changes(member_client, member_user, scoped_users):
    *_, stranger, role = scoped_users
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    response = member_client.post('/api/v1/users/bulk_action/', {'action': 'deactivate', 'user_ids': [str(member_user.pk), str(stranger.pk)]}, format='json')
    assert response.status_code == 403
    assert response.json()['data'] == {'atomic': True, 'succeeded': 0, 'failed': 2,
        'results': [{'id': str(identifier), 'status': 403} for identifier in [member_user.pk, stranger.pk]]}
    member_user.refresh_from_db()
    stranger.refresh_from_db()
    assert member_user.is_active and stranger.is_active
    assert member_client.post('/api/v1/users/', {'username': 'blocked', 'email': 'b@example.com', 'password': 'SecureGenerated#3478'}, format='json').status_code == 403
    assert member_client.post('/api/v1/data-io/import/', {'resource': 'users', 'file': SimpleUploadedFile('users.csv', b'username,email\na,a@example.com')}, format='multipart').status_code == 403


def test_scope_file_download_delete_task_cancel_logs_and_dashboard(member_client, member_user, scoped_users):
    grant_files(member_user, 'file:download')
    root, child, outside, team, stranger, role = scoped_users
    for resource in ['file', 'task', 'log']:
        DataScopeGrant.objects.create(role=role, resource=resource, scope='department_tree')
    owned = FileModel.objects.create(uploader=team, original_name='team.txt', file=SimpleUploadedFile('team.txt', b'owned'))
    hidden = FileModel.objects.create(uploader=stranger, original_name='outside.txt', file=SimpleUploadedFile('outside.txt', b'outside'))
    downloaded = member_client.get(f'/api/v1/files/{owned.pk}/download/')
    assert downloaded.status_code == 200
    downloaded.close()
    assert member_client.get(f'/api/v1/files/{hidden.pk}/download/').status_code == 404
    assert member_client.delete(f'/api/v1/files/{hidden.pk}/').status_code == 404
    assert member_client.delete(f'/api/v1/files/{owned.pk}/').status_code == 204
    task = TaskRecord.objects.create(creator=stranger, name='外部')
    assert member_client.post(f'/api/v1/tasks/{task.pk}/cancel/').status_code == 404
    hidden_log = OperationLog.objects.create(user=stranger, action='read', resource='fixture', ip_address='127.0.0.1')
    assert member_client.get(f'/api/v1/logs/operation/{hidden_log.pk}/').status_code == 404
    stats = member_client.get('/api/v1/dashboard/stats/').json()['data']
    assert stats['totals']['files'] == 0 and stats['task_status'] == {}


def test_scope_survives_org_disabled_and_refreshes_without_login(member_client, member_user, scoped_users):
    *_, role = scoped_users
    grant = DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    assert member_client.get('/api/v1/users/').json()['data']['pagination']['total'] == 1
    with override_settings(ADMINCORE_MODULES=()):
        assert member_client.get('/api/v1/users/').json()['data']['pagination']['total'] == 1
    grant.scope = 'all'
    grant.save()
    assert member_client.get('/api/v1/users/').json()['data']['pagination']['total'] == 3


def test_inactive_scoped_role_does_not_expand_access(member_client, member_user, scoped_users):
    from apps.core.data_scope import unrestricted_user_creation
    *_, role = scoped_users
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    legacy = Role.objects.create(name='保留查询权限')
    UserRole.objects.create(user=member_user, role=legacy)
    for action in ['read', 'update']:
        permission = Permission.objects.get(code='user:' + action)
        RolePermission.objects.create(role=legacy, permission=permission)
    role.is_active = False
    role.save()
    assert member_client.get('/api/v1/users/').json()['data']['pagination']['total'] == 0
    assert not unrestricted_user_creation(member_user)
    role.is_active = True
    role.save()
    assert member_client.get('/api/v1/users/').json()['data']['pagination']['total'] == 1


def test_scoped_user_delete_and_role_union(member_client, member_user, scoped_users):
    root, child, outside, team, stranger, role = scoped_users
    DataScopeGrant.objects.create(role=role, resource='user', scope='department_tree')
    second = Role.objects.create(name='另一部门范围')
    UserRole.objects.create(user=member_user, role=second)
    grant = DataScopeGrant.objects.create(role=second, resource='user', scope='custom')
    grant.departments.add(outside)
    assert member_client.get('/api/v1/users/').json()['data']['pagination']['total'] == 3
    second.is_active = False
    second.save()
    assert member_client.delete(f'/api/v1/users/{stranger.pk}/').status_code == 404
    assert member_client.delete(f'/api/v1/users/{team.pk}/').status_code == 200
    assert not User.objects.filter(pk=team.pk).exists()


def test_import_stops_if_scope_is_revoked_between_rows(member_user, scoped_users, monkeypatch):
    from apps.data_io.tasks import run_data_import
    from apps.data_io.resources import get_resource
    *_, role = scoped_users
    grant = DataScopeGrant.objects.create(role=role, resource='user', scope='all')
    source = FileModel.objects.create(uploader=member_user, original_name='users.csv', file=SimpleUploadedFile('users.csv', b'username,email\ncreated_1,a@example.com\ncreated_2,b@example.com'))
    record = TaskRecord.objects.create(creator=member_user, name='导入', related_resource='users', result={'file_id': str(source.pk)})
    config = dict(get_resource('users'))
    original = config['create_row']
    def create_and_revoke(data):
        result = original(data)
        grant.scope = 'self'
        grant.save()
        return result
    config['create_row'] = create_and_revoke
    monkeypatch.setattr('apps.data_io.resources.get_resource', lambda _: config)
    run_data_import(str(record.pk))
    record.refresh_from_db()
    assert record.status == 'failed' and record.result['created'] == 1
    assert User.objects.filter(username='created_1').exists() and not User.objects.filter(username='created_2').exists()


def test_role_edit_cannot_be_used_to_escape_data_scope(member_client, member_user, scoped_users):
    *_, role = scoped_users
    permission = Permission.objects.create(name='角色维护', code='role:update', resource='role', action='update')
    RolePermission.objects.create(role=role, permission=permission)
    for method in ['patch', 'delete']:
        response = getattr(member_client, method)(f'/api/v1/permissions/roles/{role.pk}/', {'is_active': False}, format='json')
        assert response.status_code == 403
    role.refresh_from_db()
    assert role.is_active


def test_scoped_import_rechecks_permission_at_execution(member_user, scoped_users):
    from apps.data_io.tasks import run_data_import
    *_, role = scoped_users
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    record = TaskRecord.objects.create(name='权限变化前提交', creator=member_user, related_resource='users')
    run_data_import(str(record.pk))
    record.refresh_from_db()
    assert record.status == 'failed' and record.error == 'execution_not_authorized'
