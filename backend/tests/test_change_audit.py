"""审计投影、事务一致性、关联 ID、访问边界及批量结果。"""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model

from apps.logs.audit import project, write_audit
from apps.logs.context import request_id
from apps.logs.models import OperationLog
from apps.permissions.models import Permission
from apps.tasks.models import TaskRecord, MaintenanceRequest

pytestmark = pytest.mark.django_db


def test_update_records_safe_before_after_and_response_request_id(admin_client, member_user):
    response = admin_client.patch(f'/api/v1/users/{member_user.pk}/',
        {'is_active': False, 'email': 'private@example.test', 'phone': '13812345678'}, format='json', HTTP_X_REQUEST_ID='audit-fixture-1')
    assert response.status_code == 200
    row = OperationLog.objects.get(resource='user', resource_id=str(member_user.pk))
    assert row.audit_version == 1 and row.request_id == response['X-Request-ID'] == 'audit-fixture-1'
    assert row.before_values['is_active'] is True and row.after_values['is_active'] is False
    assert row.actor_identifier == str(row.user_id)
    assert 'private@example.test' not in str(row.__dict__) and '13812345678' not in str(row.__dict__)
    assert request_id.get() == ''


def test_request_context_not_reused_after_request(admin_client, member_user):
    admin_client.patch(f'/api/v1/users/{member_user.pk}/', {'is_active': False}, format='json', HTTP_X_REQUEST_ID='first-request')
    response = admin_client.patch(f'/api/v1/users/{member_user.pk}/', {'is_active': True}, format='json')
    row = OperationLog.objects.filter(resource='user').latest('created_at')
    assert row.request_id == response['X-Request-ID'] and row.request_id != 'first-request'
    assert request_id.get() == ''


def test_async_request_context_and_exception_are_reset():
    import asyncio
    from django.http import HttpResponse
    from django.test import RequestFactory
    from apps.core.middleware import RequestTrackingMiddleware
    async def run():
        async def respond(request):
            await asyncio.sleep(0)
            assert request_id.get() == request.request_id
            if request.path == '/fail':
                raise RuntimeError('fixture')
            return HttpResponse()
        middleware = RequestTrackingMiddleware(respond)
        async def send(path, identifier):
            request = RequestFactory().get(path, HTTP_X_REQUEST_ID=identifier)
            try:
                response = await middleware(request)
                assert response['X-Request-ID'] == identifier
            except RuntimeError:
                assert path == '/fail'
            assert request_id.get() == ''
        await asyncio.gather(send('/ok', 'async-ok'), send('/fail', 'async-fail'))
    asyncio.run(run())


@pytest.mark.parametrize('operation', ['create', 'update', 'delete'])
def test_user_change_rolls_back_if_audit_unavailable(admin_client, member_user, operation):
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('private credential')):
        if operation == 'create':
            response = admin_client.post('/api/v1/users/', {'username': 'audit-rollback', 'password': 'A-Safe-Test#Password9137'}, format='json')
            assert not get_user_model().objects.filter(username='audit-rollback').exists()
        elif operation == 'update':
            response = admin_client.patch(f'/api/v1/users/{member_user.pk}/', {'is_active': False}, format='json')
            member_user.refresh_from_db()
            assert member_user.is_active
        else:
            response = admin_client.delete(f'/api/v1/users/{member_user.pk}/')
            assert get_user_model().objects.filter(pk=member_user.pk).exists()
    assert response.status_code == 500 and 'private' not in response.content.decode()


def test_role_permission_assignment_and_deletion_have_snapshots(admin_client):
    permission = Permission.objects.create(name='Audit read', resource='fixture', action='read', code='fixture:read')
    response = admin_client.post('/api/v1/permissions/roles/', {'name': 'audit-role', 'permission_ids': [str(permission.pk)]}, format='json')
    assert response.status_code == 201
    identifier = response.json()['data']['id']
    created = OperationLog.objects.get(resource='role', resource_id=identifier)
    assert created.before_values is None and created.after_values['permission_ids'] == [str(permission.pk)]
    assert admin_client.patch(f'/api/v1/permissions/roles/{identifier}/', {'permission_ids': [], 'is_active': False}, format='json').status_code == 200
    updated = OperationLog.objects.filter(resource='role').latest('created_at')
    assert updated.before_values['permission_ids'] == [str(permission.pk)] and updated.after_values['permission_ids'] == []
    assert admin_client.delete(f'/api/v1/permissions/roles/{identifier}/').status_code == 200
    deleted = OperationLog.objects.filter(resource='role').latest('created_at')
    assert deleted.before_values['is_active'] is False and deleted.after_values is None


def test_bulk_result_and_each_before_after_share_request(admin_client, member_user):
    response = admin_client.post('/api/v1/users/bulk_action/', {'action': 'deactivate', 'user_ids': [str(member_user.pk)]},
                                 format='json', HTTP_X_REQUEST_ID='bulk-audit')
    assert response.status_code == 200
    logs = OperationLog.objects.filter(request_id='bulk-audit')
    assert logs.count() == 2
    summary = logs.get(resource_id='')
    assert summary.batch_results == [{'id': str(member_user.pk), 'status': 200}]
    assert logs.get(resource_id=str(member_user.pk)).before_values['is_active'] is True
    assert logs.get(resource_id=str(member_user.pk)).after_values['is_active'] is False


def test_bulk_failure_rolls_back_and_rejection_is_audited(admin_client, member_user):
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('audit unavailable')):
        response = admin_client.post('/api/v1/users/bulk_action/', {'action': 'deactivate', 'user_ids': [str(member_user.pk)]}, format='json')
    assert response.status_code == 500
    member_user.refresh_from_db()
    assert member_user.is_active
    response = admin_client.post('/api/v1/users/bulk_action/', {'action': 'deactivate', 'user_ids': [str(member_user.pk), str(uuid4())]},
                                 format='json', HTTP_X_REQUEST_ID='rejected-batch')
    assert response.status_code == 403
    row = OperationLog.objects.get(request_id='rejected-batch')
    assert row.status == 403 and all(item['status'] == 403 for item in row.batch_results)
    member_user.refresh_from_db()
    assert member_user.is_active


def test_reset_password_audits_state_but_never_secret(admin_client, member_user):
    password = 'Private#AuditPassword1479'
    response = admin_client.post(f'/api/v1/users/{member_user.pk}/reset_password/',
                                 {'password': password, 'must_change_password': True}, format='json')
    assert response.status_code == 200
    row = OperationLog.objects.get(resource='user', description='reset_password')
    assert row.after_values['session_version'] == row.before_values['session_version'] + 1
    assert row.after_values['must_change_password'] is True
    assert password not in str(row.__dict__) and 'password' not in row.before_values


def test_unknown_and_private_projection_fields_cannot_leak():
    assert project('user', {'is_active': True, 'password': 'secret', 'email': 'private', 'private_key': 'secret'}) == {'is_active': True}
    with pytest.raises(ValueError):
        project('unregistered', {'secret': 'private'})
    with pytest.raises(ValueError):
        project('system_config', {'value': 'x' * 40000})


def test_legacy_records_keep_version_zero_and_new_trace_stamps_celery(admin_user):
    row = OperationLog.objects.create(user=admin_user, action='read', resource='legacy', ip_address='127.0.0.1')
    assert row.audit_version == 0 and row.before_values is None
    record = TaskRecord.objects.create(name='audit task', creator=admin_user, celery_task_id='celery-fixture')
    MaintenanceRequest.objects.create(record=record, key='lifecycle', options={'dry_run': False},
                                      session_version=admin_user.session_version, request_id='origin-request')
    row = write_audit(resource='lifecycle', action='delete', actor=admin_user, record=record, before={'category': 'login', 'count': 1, 'ids': [str(uuid4())]})
    assert row.task_id == 'celery-fixture' and row.task_record_id == record.pk and row.request_id == 'origin-request'


def test_deleted_actor_identifier_survives_account_deletion(admin_user):
    identifier = str(admin_user.pk)
    row = write_audit(resource='user', actor=admin_user, after={'is_active': True})
    admin_user.delete()
    row.refresh_from_db()
    assert row.user_id is None and row.actor_identifier == identifier


def test_read_only_log_endpoints_and_admin_permissions(admin_client, member_client, admin_user):
    row = write_audit(resource='user', actor=admin_user, after={'is_active': True})
    response = admin_client.get('/api/v1/logs/operation/', {'request_id': row.request_id})
    assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
    assert 'before_values' not in response.json()['data']['items'][0]
    detail = admin_client.get(f'/api/v1/logs/operation/{row.pk}/')
    assert detail.status_code == 200 and detail.json()['after_values'] == {'is_active': True}
    assert admin_client.patch(f'/api/v1/logs/operation/{row.pk}/', {'after_values': {}}, format='json').status_code == 405
    assert admin_client.delete(f'/api/v1/logs/operation/{row.pk}/').status_code == 405
    assert member_client.get('/api/v1/logs/operation/').status_code == 403
    configured = admin.site._registry[OperationLog]
    request = SimpleNamespace(user=admin_user)
    assert configured.has_view_permission(request)
    assert not any([configured.has_add_permission(request), configured.has_change_permission(request), configured.has_delete_permission(request)])


def test_role_assignment_rolls_back_with_failed_audit(admin_client):
    from apps.permissions.models import Role, RolePermission
    role = Role.objects.create(name='audit-role-rollback')
    permission = Permission.objects.create(name='Audit fixture', resource='fixture', action='read', code='fixture:read')
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('audit unavailable')):
        response = admin_client.patch(f'/api/v1/permissions/roles/{role.pk}/',
            {'permission_ids': [str(permission.pk)], 'is_active': False}, format='json')
    role.refresh_from_db()
    assert response.status_code == 500 and role.is_active
    assert not RolePermission.objects.filter(role=role).exists()


def test_announcement_hashes_track_equal_length_edits_without_body(admin_client):
    import hashlib
    base = '/api/v1/notifications/announcements/manage/'
    response = admin_client.post(base, {'title': 'Audit fixture', 'content': 'PRIVATE-A', 'version': 0}, format='json')
    assert response.status_code == 201
    identifier = response.json()['data']['id']
    response = admin_client.patch(base + identifier + '/',
        {'title': 'Audit fixture', 'content': 'PRIVATE-B', 'version': 1}, format='json')
    assert response.status_code == 200
    row = OperationLog.objects.filter(resource='announcement', resource_id=identifier).latest('created_at')
    assert row.before_values['content_length'] == row.after_values['content_length']
    assert row.before_values['content_sha256'] == hashlib.sha256(b'PRIVATE-A').hexdigest()
    assert row.after_values['content_sha256'] == hashlib.sha256(b'PRIVATE-B').hexdigest()
    assert 'PRIVATE-A' not in str(row.__dict__) and 'PRIVATE-B' not in str(row.__dict__)


def test_approval_decision_and_outbox_roll_back_with_failed_audit(admin_client, admin_user, member_user):
    from apps.approvals.models import ApprovalRequest
    from apps.core.models import OutboxEvent
    row = ApprovalRequest.objects.create(applicant=member_user, assignee=admin_user, title='private title', content='private body')
    count = OutboxEvent.objects.count()
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('audit unavailable')):
        response = admin_client.post(f'/api/v1/approvals/{row.pk}/approve/', {'comment': 'private comment'}, format='json')
    assert response.status_code == 500
    row.refresh_from_db()
    assert row.status == 'pending' and OutboxEvent.objects.count() == count


def test_registered_config_and_department_have_structured_versions(admin_client):
    response = admin_client.patch('/api/v1/system/config/files.retention_days/', {'version': 0, 'value': 45}, format='json')
    assert response.status_code == 200
    row = OperationLog.objects.get(resource='system_config', resource_id='files.retention_days')
    assert row.before_values == {'value': 30} and row.after_values == {'value': 45}
    response = admin_client.post('/api/v1/organization/departments/', {'name': '审计部门', 'version': 0}, format='json')
    assert response.status_code == 201
    identifier = response.json()['data']['id']
    row = OperationLog.objects.get(resource='department', resource_id=identifier)
    assert row.before_values is None and row.after_values['version'] == 1


def test_structured_detail_obeys_log_scope_and_module_shutdown(member_client, member_user, admin_user):
    from django.test import override_settings
    from apps.core.models import DataScopeGrant
    from apps.permissions.models import Role, RolePermission, UserRole
    permission, _ = Permission.objects.get_or_create(code='log:read', defaults={'name': 'Audit logs', 'resource': 'log', 'action': 'read'})
    role = Role.objects.create(name='scoped-audit-role')
    RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=member_user, role=role)
    DataScopeGrant.objects.create(role=role, resource='log', scope='self')
    own = write_audit(resource='user', actor=member_user, after={'is_active': True})
    hidden = write_audit(resource='user', actor=admin_user, after={'is_active': True})
    with override_settings(ADMINCORE_MODULES=()):
        assert member_client.get(f'/api/v1/logs/operation/{own.pk}/').status_code == 200
        assert member_client.get(f'/api/v1/logs/operation/{hidden.pk}/').status_code == 404
    request = SimpleNamespace(user=member_user)
    assert list(admin.site._registry[OperationLog].get_queryset(request).values_list('pk', flat=True)) == [own.pk]
