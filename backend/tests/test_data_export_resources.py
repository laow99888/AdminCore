"""跨资源批量下载的权限、范围、敏感字段与完整性契约。"""
import csv
import io
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from openpyxl import load_workbook

from apps.core.models import DataScopeGrant, Department, OrganizationMembership
from apps.files.models import FileModel
from apps.logs.models import OperationLog, LoginLog, ExceptionLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.tasks.models import TaskRecord
from apps.data_io.tasks import run_data_import


def grant(user, *codes):
    role = Role.objects.create(name=f'export-{Role.objects.count()}')
    UserRole.objects.create(user=user, role=role)
    for code in codes:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': code, 'resource': resource, 'action': action})
        RolePermission.objects.create(role=role, permission=permission)
    return role


def rows(response, format='csv'):
    assert response.status_code == 200, response.content
    if format == 'csv':
        return list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    return list(load_workbook(io.BytesIO(response.content), data_only=False).active.values)


@pytest.mark.django_db
class TestExportResources:
    def test_resource_directory_and_denials_cannot_be_cached(self, admin_client, member_client):
        from rest_framework.test import APIClient
        responses = [admin_client.get('/api/v1/data-io/resources/'),
                     member_client.get('/api/v1/data-io/resources/'),
                     APIClient().get('/api/v1/data-io/resources/'),
                     member_client.get('/api/v1/data-io/export/?resource=roles')]
        assert [response.status_code for response in responses] == [200, 200, 401, 403]
        assert all(response['Cache-Control'] == 'private, no-store' for response in responses)

    @pytest.mark.parametrize(('resource', 'permission'), [('users', 'user:read'), ('roles', 'role:read'), ('logs', 'log:read'), ('files', 'file:download')])
    def test_export_requires_both_permissions(self, member_client, member_user, resource, permission):
        role = grant(member_user, 'data_io:export')
        url = f'/api/v1/data-io/export/?resource={resource}'
        assert member_client.get(url).status_code == 403
        resource_perm = Permission.objects.create(name=permission, code=permission, resource=permission.split(':')[0], action=permission.split(':')[1])
        RolePermission.objects.create(role=role, permission=resource_perm)
        assert member_client.get(url).status_code == 200
        RolePermission.objects.filter(role=role, permission__code='data_io:export').delete()
        assert member_client.get(url).status_code == 403

    def test_directory_declares_export_only_and_filters_permissions(self, admin_client, member_client, member_user):
        data = admin_client.get('/api/v1/data-io/resources/').json()['data']
        assert {item['resource'] for item in data['resources']} == {'users', 'roles', 'logs', 'files'}
        assert [item['resource'] for item in data['resources'] if item['importable']] == ['users']
        assert data['max_rows'] == 5000 and data['max_bytes'] == 10485760
        grant(member_user, 'data_io:export', 'log:read')
        allowed = member_client.get('/api/v1/data-io/resources/').json()['data']['resources']
        assert allowed == [{'resource': 'logs', 'label': '日志', 'importable': False, 'exportable': True}]

    @pytest.mark.parametrize('resource', ['roles', 'logs', 'files'])
    def test_export_only_resources_cannot_template_import_retry_or_execute(self, admin_client, admin_user, resource):
        uploaded = io.BytesIO(b'name\nexample\n')
        uploaded.name = 'data.csv'
        assert admin_client.get(f'/api/v1/data-io/template/?resource={resource}').status_code == 400
        assert admin_client.post('/api/v1/data-io/import/', {'resource': resource, 'file': uploaded}, format='multipart').status_code == 400
        task = TaskRecord.objects.create(name='unsafe retry fixture', task_type='import', related_resource=resource, creator=admin_user, result={'file_id': 'not-a-file'})
        assert admin_client.post(f'/api/v1/data-io/import/{task.pk}/').status_code == 400
        run_data_import(str(task.pk))
        task.refresh_from_db()
        assert task.status == 'failed'
        assert '导入资源' in task.error

    @pytest.mark.parametrize('format', ['csv', 'xlsx'])
    def test_roles_only_basic_metadata_formula_safe_and_boolean_preserved(self, admin_client, format):
        role = Role.objects.create(name='=SUM(1,2)', description='  +hidden', is_active=False)
        result = rows(admin_client.get(f'/api/v1/data-io/export/?resource=roles&export_format={format}&is_active=false'), format)
        assert list(result[0]) == ['id', 'name', 'description', 'is_active', 'created_at']
        assert len(result) == 2 and result[1][0] == str(role.pk)
        assert list(result[1][1:4]) == ["'=SUM(1,2)", "'  +hidden", 'False']

    @pytest.mark.parametrize(('kind', 'model', 'data', 'sensitive'), [
        ('operation', OperationLog, {'action': 'update', 'resource': 'user', 'description': 'secret-password', 'resource_id': 'item'}, ['description', 'user_agent']),
        ('login', LoginLog, {'username': 'fixture', 'status': 'failed', 'error_message': 'secret-password'}, ['error_message', 'user_agent']),
        ('exception', ExceptionLog, {'level': 'error', 'message': 'secret-password', 'traceback': 'secret-stack', 'request_path': '/?token=private', 'request_method': 'GET'}, ['message', 'traceback', 'request_path']),
    ])
    @pytest.mark.parametrize('format', ['csv', 'xlsx'])
    def test_all_log_kinds_have_metadata_only(self, admin_client, member_user, kind, model, data, sensitive, format):
        record = model.objects.create(user=member_user, ip_address='127.0.0.1', **data)
        result = rows(admin_client.get(f'/api/v1/data-io/export/?resource=logs&log_type={kind}&export_format={format}'), format)
        assert all(field not in result[0] for field in sensitive)
        assert any(row[0] == str(record.pk) for row in result[1:])
        assert 'secret-password' not in str(result) and 'private' not in str(result)
        if kind != 'login':
            assert 'member' in str(result)

    def test_files_metadata_scope_private_and_deleted_excluded(self, admin_client, member_client, member_user, admin_user):
        grant(member_user, 'data_io:export', 'file:download')
        visible = FileModel.objects.create(original_name='own.pdf', file='private-storage/own.pdf', file_type='pdf', uploader=member_user, size=0)
        FileModel.objects.create(original_name='other.pdf', file='secret-path', file_type='pdf', uploader=admin_user)
        FileModel.objects.create(original_name='avatar.png', file='private-avatar', file_type='png', purpose='avatar', uploader=member_user)
        FileModel.objects.create(original_name='deleted.pdf', file='deleted-path', file_type='pdf', is_deleted=True, uploader=member_user)
        result = rows(member_client.get('/api/v1/data-io/export/?resource=files'))
        assert len(result) == 2 and result[1][0] == str(visible.pk)
        assert result[1][3] == '0'
        assert not {'file', 'md5', 'description', 'purpose', 'is_deleted'} & set(result[0])
        assert 'private-storage' not in str(result)
        admin_result = rows(admin_client.get('/api/v1/data-io/export/?resource=files'))
        assert len(admin_result) == 3

    @pytest.mark.parametrize('resource', ['users', 'logs', 'files'])
    def test_explicit_self_scope_never_leaks_other_owners(self, member_client, member_user, admin_user, resource):
        perms = {'users': 'user:read', 'logs': 'log:read', 'files': 'file:download'}
        role = grant(member_user, 'data_io:export', perms[resource])
        DataScopeGrant.objects.create(role=role, resource={'users': 'user', 'logs': 'log', 'files': 'file'}[resource], scope='self')
        if resource == 'logs':
            for owner in (member_user, admin_user):
                OperationLog.objects.create(user=owner, action='read', resource='fixture', ip_address='127.0.0.1')
        elif resource == 'files':
            for owner in (member_user, admin_user):
                FileModel.objects.create(uploader=owner, original_name='fixture', file_type='txt')
        result = rows(member_client.get(f'/api/v1/data-io/export/?resource={resource}'))
        assert len(result) == 2
        assert 'member' in str(result) and 'admin' not in str(result)

    def test_department_scope_and_disabled_grant_remain_restricted(self, member_client, member_user):
        role = grant(member_user, 'data_io:export', 'user:read')
        department = Department.objects.create(name='owned')
        other = Department.objects.create(name='other')
        OrganizationMembership.objects.create(user=member_user, department=department)
        colleague = get_user_model().objects.create_user('colleague', 'colleague@example.test')
        outsider = get_user_model().objects.create_user('outsider', 'outsider@example.test')
        OrganizationMembership.objects.create(user=colleague, department=department)
        OrganizationMembership.objects.create(user=outsider, department=other)
        DataScopeGrant.objects.create(role=role, resource='user', scope='department')
        result = rows(member_client.get('/api/v1/data-io/export/?resource=users'))
        assert len(result) == 3 and 'outsider' not in str(result)
        # 另一个有效角色保留精确权限，范围所属角色停用不能回落全量。
        grant(member_user, 'data_io:export', 'user:read')
        role.is_active = False
        role.save()
        assert len(rows(member_client.get('/api/v1/data-io/export/?resource=users'))) == 1

    @pytest.mark.parametrize('query', [
        'resource=missing', 'resource=roles&is_active=yes', 'resource=users&ordering=password',
        'resource=files&uploader=private', 'resource=files&file_type=../secret', 'resource=logs&log_type=bad',
        'resource=logs&log_type=login&action=delete', 'resource=logs&action=arbitrary',
        'resource=logs&log_type=exception&request_method=WRONG', 'resource=users&search=a&search=b',
        'resource=users&export_format=CSV', 'resource=users&search=' + 'a' * 201,
    ])
    def test_strict_filter_validation(self, admin_client, query):
        assert admin_client.get('/api/v1/data-io/export/?' + query).status_code == 400

    def test_search_filter_matches_list_terms_and_boolean(self, admin_client):
        get_user_model().objects.create_user('alpha', 'alpha@example.test', first_name='one', is_active=False)
        get_user_model().objects.create_user('alpha2', 'alpha2@example.test', first_name='two')
        result = rows(admin_client.get('/api/v1/data-io/export/?resource=users&search=alpha%20one&is_active=false'))
        assert len(result) == 2 and result[1][0] == 'alpha'

    def test_log_filter_maps_resource_without_conflicting_export_resource(self, admin_client, member_user):
        OperationLog.objects.create(user=member_user, resource='safe', action='read', ip_address='127.0.0.1')
        result = rows(admin_client.get('/api/v1/data-io/export/?resource=logs&resource_name=safe&action=read'))
        assert len(result) == 2 and result[1][4] == 'safe'

    def test_related_uploader_export_does_not_add_queries_per_row(self, admin_client, member_user):
        FileModel.objects.create(original_name='first', file_type='txt', uploader=member_user)
        with CaptureQueriesContext(connection) as small:
            assert admin_client.get('/api/v1/data-io/export/?resource=files').status_code == 200
        FileModel.objects.bulk_create([FileModel(original_name=f'bulk-{index}', file_type='txt', uploader=member_user) for index in range(40)])
        with CaptureQueriesContext(connection) as large:
            result = rows(admin_client.get('/api/v1/data-io/export/?resource=files'))
        assert len(result) == 42
        assert len(large) <= len(small) + 1

    @pytest.mark.parametrize('format', ['csv', 'xlsx'])
    @pytest.mark.parametrize('limit', ['rows', 'bytes'])
    def test_limits_reject_entire_export_without_success_audit(self, admin_client, member_user, format, limit):
        kwargs = {'EXPORT_MAX_ROWS': 0} if limit == 'rows' else {'EXPORT_MAX_BYTES': 1}
        with patch.multiple('apps.data_io.views', **kwargs):
            response = admin_client.get(f'/api/v1/data-io/export/?resource=users&export_format={format}')
        assert response.status_code == 413 and '未生成部分文件' in response.json()['message']
        assert not OperationLog.objects.filter(resource='data_io', action='export').exists()

    @pytest.mark.parametrize('format', ['csv', 'xlsx'])
    def test_oversized_cell_is_rejected_not_silently_truncated(self, admin_client, format):
        Role.objects.create(name='long', description='a' * 32768)
        assert admin_client.get(f'/api/v1/data-io/export/?resource=roles&export_format={format}').status_code == 400

    def test_audit_failure_never_returns_file(self, admin_client, member_user):
        with patch('apps.data_io.views._log', side_effect=RuntimeError('audit fixture unavailable')):
            response = admin_client.get('/api/v1/data-io/export/?resource=users')
        assert response.status_code == 500
        assert 'Content-Disposition' not in response

    def test_module_shutdown_even_when_urlconf_was_preloaded(self, admin_client, settings):
        settings.ADMINCORE_MODULES = ()
        assert admin_client.get('/api/v1/data-io/export/').status_code == 404
        assert admin_client.get('/api/v1/data-io/resources/').status_code == 404
        assert admin_client.get('/api/v1/data-io/template/').status_code == 404

    def test_real_row_boundary_does_not_truncate(self, admin_client):
        Role.objects.bulk_create([Role(name=f'bulk-{index}') for index in range(5001)])
        response = admin_client.get('/api/v1/data-io/export/?resource=roles')
        assert response.status_code == 413
        assert not OperationLog.objects.filter(resource='data_io', action='export').exists()
        Role.objects.filter(name='bulk-5000').delete()
        response = admin_client.get('/api/v1/data-io/export/?resource=roles')
        assert len(rows(response)) == 5001

    def test_empty_export_has_headers_and_no_store(self, admin_client):
        response = admin_client.get('/api/v1/data-io/export/?resource=roles')
        assert len(rows(response)) == 1
        assert response['Cache-Control'] == 'private, no-store'
        assert OperationLog.objects.filter(resource='data_io', action='export').count() == 1
