"""真实 Django admin 表单、内联授权、改密及批量 action 的审计事务。"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def browser(client, admin_user):
    client.force_login(admin_user)
    return client


def role_form(name, permission):
    return {'name': name, 'description': '', 'is_active': 'on', '_save': '保存',
            'permissions-TOTAL_FORMS': '1', 'permissions-INITIAL_FORMS': '0',
            'permissions-MIN_NUM_FORMS': '0', 'permissions-MAX_NUM_FORMS': '1000',
            'permissions-0-permission': str(permission.pk)}


def test_role_inline_permission_is_recorded_after_related_save(browser):
    permission = Permission.objects.create(name='Admin audit', code='fixture:read', resource='fixture', action='read')
    response = browser.post('/admin/permissions/role/add/', role_form('admin-audit-role', permission), HTTP_X_REQUEST_ID='admin-create-role')
    assert response.status_code == 302
    role = Role.objects.get(name='admin-audit-role')
    row = OperationLog.objects.get(resource='role', request_id='admin-create-role')
    assert row.before_values is None and row.after_values['permission_ids'] == [str(permission.pk)]
    assert row.description == 'django_admin:create'
    link = RolePermission.objects.get(role=role)
    payload = role_form('admin-audit-updated', permission)
    payload.update({'edit_version': role.version, 'permissions-INITIAL_FORMS': '1', 'permissions-0-id': str(link.pk),
                    'permissions-0-role': str(role.pk), 'permissions-0-DELETE': 'on'})
    response = browser.post(f'/admin/permissions/role/{role.pk}/change/', payload, HTTP_X_REQUEST_ID='admin-update-role')
    assert response.status_code == 302
    row = OperationLog.objects.get(request_id='admin-update-role')
    assert row.before_values['name'] == 'admin-audit-role' and row.after_values['name'] == 'admin-audit-updated'
    assert row.before_values['permission_ids'] == [str(permission.pk)] and row.after_values['permission_ids'] == []


def test_admin_role_create_rolls_back_inline_and_django_log_when_audit_fails(browser):
    from django.contrib.admin.models import LogEntry
    permission = Permission.objects.create(name='Rollback', code='fixture:read', resource='fixture', action='read')
    previous = LogEntry.objects.count()
    with patch('apps.logs.admin_audit.write_audit', side_effect=RuntimeError('private fixture')):
        response = browser.post('/admin/permissions/role/add/', role_form('admin-audit-rollback', permission))
    assert response.status_code == 500 and 'private fixture' not in response.content.decode()
    assert not Role.objects.filter(name='admin-audit-rollback').exists()
    assert not RolePermission.objects.exists() and LogEntry.objects.count() == previous


@pytest.mark.parametrize('bulk', [False, True])
def test_admin_deletion_and_audit_fail_as_one_transaction(browser, bulk):
    roles = [Role.objects.create(name='admin-delete-' + str(i)) for i in range(2 if bulk else 1)]
    url = '/admin/permissions/role/' if bulk else f'/admin/permissions/role/{roles[0].pk}/delete/'
    payload = {'post': 'yes', 'action': 'delete_selected', '_selected_action': [str(row.pk) for row in roles]}
    with patch('apps.logs.admin_audit.write_audit', side_effect=RuntimeError('fixture audit unavailable')):
        response = browser.post(url, payload)
    assert response.status_code == 500
    assert Role.objects.filter(pk__in=[row.pk for row in roles]).count() == len(roles)
    response = browser.post(url, payload, HTTP_X_REQUEST_ID='admin-delete-batch')
    assert response.status_code == 302
    assert not Role.objects.filter(pk__in=[row.pk for row in roles]).exists()
    logs = OperationLog.objects.filter(request_id='admin-delete-batch')
    assert logs.exclude(resource_id='').count() == len(roles)
    assert all(row.after_values is None for row in logs)
    if bulk:
        assert sorted(item['id'] for item in logs.get(resource_id='').batch_results) == sorted(str(row.pk) for row in roles)


def test_admin_password_change_is_atomic_and_does_not_log_secret(browser, member_user):
    url = f'/admin/auth_app/user/{member_user.pk}/password/'
    password = 'Admin-Private#Fixture1497'
    original = member_user.password
    with patch('apps.logs.admin_audit.write_audit', side_effect=RuntimeError('audit unavailable')):
        response = browser.post(url, {'password1': password, 'password2': password, 'usable_password': 'true'})
    assert response.status_code == 500
    member_user.refresh_from_db()
    assert member_user.password == original
    response = browser.post(url, {'password1': password, 'password2': password, 'usable_password': 'true'}, HTTP_X_REQUEST_ID='admin-password-change')
    assert response.status_code == 302
    member_user.refresh_from_db()
    assert member_user.check_password(password)
    row = OperationLog.objects.get(request_id='admin-password-change')
    assert row.after_values['session_version'] == row.before_values['session_version'] + 1
    assert row.after_values['must_change_password'] is True
    assert password not in str(row.__dict__) and member_user.password not in str(row.__dict__)


def test_user_role_admin_write_is_recorded(browser, member_user):
    role = Role.objects.create(name='admin-user-role')
    response = browser.post('/admin/permissions/userrole/add/', {'user': member_user.pk, 'role': role.pk, '_save': '保存'})
    assert response.status_code == 302
    link = UserRole.objects.get(user=member_user, role=role)
    row = OperationLog.objects.get(resource='user_role', resource_id=str(link.pk))
    assert row.after_values['role_id'] == str(role.pk) and row.after_values['user_id'] == str(member_user.pk)


def test_disabled_optional_module_hides_admin_model_and_denies_writes(admin_user):
    from apps.files.models import FileModel
    from apps.notifications.models import Notification
    from apps.tasks.models import TaskRecord
    request = SimpleNamespace(user=admin_user)
    with override_settings(ADMINCORE_MODULES=()):
        for model in (FileModel, Notification, TaskRecord):
            configured = admin.site._registry[model]
            assert not any([configured.has_module_permission(request), configured.has_view_permission(request),
                            configured.has_add_permission(request), configured.has_change_permission(request), configured.has_delete_permission(request)])


def test_admin_cannot_accept_more_than_registered_bulk_limit(browser):
    from apps.logs.admin_audit import AuditedAdminMixin
    from django.core.exceptions import PermissionDenied
    configured = admin.site._registry[Role]
    request = SimpleNamespace(user=get_user_model().objects.get(username='admin'))
    with pytest.raises(PermissionDenied):
        AuditedAdminMixin.log_deletions(configured, request, [SimpleNamespace(pk=i) for i in range(1001)])


def test_admin_bulk_partial_audit_failure_rolls_back_prior_log(browser):
    from apps.logs.audit import write_audit
    roles = [Role.objects.create(name='admin-partial-' + str(i)) for i in range(2)]
    count = OperationLog.objects.count()
    attempts = 0
    def record_then_fail(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError('second audit fixture')
        return write_audit(**kwargs)
    with patch('apps.logs.admin_audit.write_audit', side_effect=record_then_fail):
        response = browser.post('/admin/permissions/role/',
            {'post': 'yes', 'action': 'delete_selected', '_selected_action': [row.pk for row in roles]})
    assert response.status_code == 500 and attempts == 2
    assert Role.objects.filter(pk__in=[row.pk for row in roles]).count() == 2
    assert OperationLog.objects.count() == count


@pytest.mark.parametrize('kind', ['role', 'menu'])
@pytest.mark.parametrize('submitted', [None, 1])
def test_admin_requires_current_edit_version_and_advances_it(browser, kind, submitted):
    from apps.permissions.models import Menu
    model = Role if kind == 'role' else Menu
    row = model.objects.create(name='admin-version-fixture', **({'path': '/admin-version-fixture'} if kind == 'menu' else {}))
    url = f'/admin/permissions/{kind}/{row.pk}/change/'
    initial = browser.get(url)
    assert initial.status_code == 200 and 'name="edit_version" value="1"' in initial.content.decode()
    model.objects.filter(pk=row.pk).update(name='concurrent latest', version=2)
    payload = {'name': 'local draft', 'description': '', 'is_active': 'on', '_save': '保存',
               'permissions-TOTAL_FORMS': '0', 'permissions-INITIAL_FORMS': '0',
               'permissions-MIN_NUM_FORMS': '0', 'permissions-MAX_NUM_FORMS': '1000'} if kind == 'role' else {
               'name': 'local draft', 'path': row.path, 'icon': '', 'order': 0, 'parent': '',
               'permission': '', 'is_visible': 'on', '_save': '保存'}
    if submitted is not None:
        payload['edit_version'] = submitted
    response = browser.post(url, payload, HTTP_X_REQUEST_ID='admin-stale-version')
    assert response.status_code == 200
    assert '内容已被其他人修改' in response.content.decode()
    row.refresh_from_db()
    assert row.name == 'concurrent latest' and row.version == 2
    assert not OperationLog.objects.filter(request_id='admin-stale-version').exists()
    payload['edit_version'] = 2
    response = browser.post(url, payload, HTTP_X_REQUEST_ID='admin-current-version')
    assert response.status_code == 302
    row.refresh_from_db()
    assert row.name == 'local draft' and row.version == 3
    assert OperationLog.objects.filter(request_id='admin-current-version', resource=kind).exists()
