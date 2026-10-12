"""全量复核中安全、状态机与跨层契约缺陷的回归测试。"""
import csv
import io
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.approvals.models import ApprovalRequest
from apps.data_io.tasks import run_data_import
from apps.files.models import FileModel
from apps.notifications.models import Notification
from apps.permissions.models import Menu, Permission, Role, RolePermission, UserRole
from apps.tasks.models import TaskRecord

pytestmark = pytest.mark.django_db
User = get_user_model()


def credentials(user, password):
    client = APIClient()
    tokens = client.post('/api/v1/auth/login/', {'username': user.username, 'password': password}, format='json').json()
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + tokens['access'])
    return client, tokens


def test_refresh_rotation_rejects_replay(member_user):
    client, tokens = credentials(member_user, 'Member#12345')
    anonymous = APIClient()
    refreshed = anonymous.post('/api/v1/auth/refresh/', {'refresh': tokens['refresh']}, format='json')
    assert refreshed.status_code == 200
    assert refreshed.json()['data']['refresh'] != tokens['refresh']
    assert anonymous.post('/api/v1/auth/refresh/', {'refresh': tokens['refresh']}, format='json').status_code == 400


def test_logout_revokes_access_and_refresh(member_user):
    client, tokens = credentials(member_user, 'Member#12345')
    assert client.post('/api/v1/auth/logout/').status_code == 200
    assert client.get('/api/v1/auth/me/').status_code == 401
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': tokens['refresh']}, format='json').status_code == 400


@pytest.mark.parametrize('admin_reset', [False, True])
def test_password_changes_revoke_tokens(member_user, admin_client, admin_reset):
    client, tokens = credentials(member_user, 'Member#12345')
    if admin_reset:
        response = admin_client.post(f'/api/v1/users/{member_user.pk}/reset_password/', {'password': 'NewStrong#87912'}, format='json')
    else:
        response = client.post('/api/v1/auth/change_password/', {
            'old_password': 'Member#12345', 'new_password': 'NewStrong#87912', 'new_password2': 'NewStrong#87912',
        }, format='json')
    assert response.status_code == 200
    assert client.get('/api/v1/auth/me/').status_code == 401
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': tokens['refresh']}, format='json').status_code == 400


def test_bootstrap_requires_explicit_safe_password(monkeypatch):
    monkeypatch.setenv('DJANGO_ENV', 'production')
    monkeypatch.delenv('ADMINCORE_ADMIN_PASSWORD', raising=False)
    with pytest.raises(CommandError):
        call_command('bootstrap_admincore')
    assert not User.objects.exists()
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'Admin#12345')
    with pytest.raises(CommandError):
        call_command('bootstrap_admincore')
    with pytest.raises(CommandError):
        call_command('bootstrap_admincore', demo=True)
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'PrivateReview#87392')
    output = io.StringIO()
    call_command('bootstrap_admincore', stdout=output)
    assert User.objects.get(username='admin').is_superuser
    assert not User.objects.filter(username='demo').exists()
    assert 'PrivateReview#87392' not in output.getvalue()
    assert not Notification.objects.filter(content__contains='PrivateReview#87392').exists()


def test_read_role_is_enforced_and_disabled_role_denied(member_client, member_user):
    permission = Permission.objects.create(name='Read users', code='user:read', resource='user', action='read')
    role = Role.objects.create(name='Reader')
    RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=member_user, role=role)
    assert member_client.get('/api/v1/users/').status_code == 200
    assert member_client.post('/api/v1/users/', {'username': 'forbidden'}, format='json').status_code == 403
    role.is_active = False
    role.save()
    assert member_client.get('/api/v1/users/').status_code == 403


def test_menu_contract_and_recursive_filter(admin_client, member_client):
    secret = Permission.objects.create(name='Secret', code='secret:read', resource='secret', action='read')
    root = Menu.objects.create(name='Public', path='/public')
    Menu.objects.create(name='Hidden child', path='/public/secret', parent=root, permission=secret)
    response = admin_client.get('/api/v1/permissions/menus/').json()
    assert isinstance(response['data']['items'], list)
    menus = member_client.get('/api/v1/permissions/menus/my_menu/').json()['data']
    assert len(menus) == 1 and menus[0]['children'] == []
    assert member_client.get('/api/v1/permissions/menus/').status_code == 403


def test_duplicate_role_permissions_preserve_original(admin_client):
    permission = Permission.objects.create(name='Read', code='user:read', resource='user', action='read')
    role = Role.objects.create(name='Reader')
    RolePermission.objects.create(role=role, permission=permission)
    result = admin_client.patch(f'/api/v1/permissions/roles/{role.pk}/', {
        'name': 'MustNotChange', 'permission_ids': [str(permission.pk), str(permission.pk)],
    }, format='json')
    assert result.status_code == 400
    role.refresh_from_db()
    assert role.name == 'Reader' and RolePermission.objects.filter(role=role).count() == 1


def import_record(admin):
    file = FileModel.objects.create(original_name='users.csv', uploader=admin,
        file=SimpleUploadedFile('users.csv', b'username,email\nreview_import,review@example.com\n'), file_type='csv')
    return TaskRecord.objects.create(name='Import', task_type='import', related_resource='users',
                                    creator=admin, result={'file_id': str(file.pk)})


def test_cancelled_import_never_writes(admin_user, admin_client):
    record = import_record(admin_user)
    record.celery_task_id = 'review-task-id'
    record.save()
    with patch('config.celery.app.control.revoke') as revoke:
        assert admin_client.post(f'/api/v1/tasks/{record.pk}/cancel/').status_code == 200
        revoke.assert_called_once_with('review-task-id', terminate=False)
    run_data_import(str(record.pk))
    record.refresh_from_db()
    assert record.status == 'cancelled'
    assert not User.objects.filter(username='review_import').exists()


def test_import_persists_queue_id_before_publish(admin_user, admin_client):
    from apps.data_io.tasks import dispatch_task
    record = import_record(admin_user)
    with patch.object(run_data_import, 'apply_async') as enqueue:
        def published(*, args, task_id):
            record.refresh_from_db()
            assert record.celery_task_id == task_id
            return type('Queued', (), {'id': task_id})()
        enqueue.side_effect = published
        assert dispatch_task(run_data_import, str(record.pk)) == record.celery_task_id


def test_revoked_import_permission_blocks_retry_and_worker(admin_user, admin_client):
    record = import_record(admin_user)
    admin_user.is_staff = admin_user.is_superuser = False
    admin_user.save()
    assert admin_client.post(f'/api/v1/data-io/import/{record.pk}/', {}, format='json').status_code == 403
    run_data_import(str(record.pk))
    record.refresh_from_db()
    assert record.status == 'failed'
    assert not User.objects.filter(username='review_import').exists()


def test_approval_stale_snapshot_cannot_overwrite(admin_user, member_user):
    application = ApprovalRequest.objects.create(title='Request', content='Full content', applicant=member_user, assignee=admin_user)
    first = ApprovalRequest.objects.get(pk=application.pk)
    second = ApprovalRequest.objects.get(pk=application.pk)
    assert first.decide(admin_user, True, 'Approved') is True
    assert second.decide(admin_user, False, 'Rejected') is False
    application.refresh_from_db()
    assert application.status == 'approved'
    notifications = Notification.objects.filter(data__request_id=str(application.pk))
    assert notifications.count() == 1 and notifications.first().data['status'] == 'approved'


def test_member_can_submit_by_exact_assignee_name(member_client, admin_user):
    response = member_client.post('/api/v1/approvals/', {'title': 'Request', 'content': 'Details',
        'assignee_username': admin_user.username}, format='json')
    assert response.status_code == 201
    assert response.json()['data']['assignee_name'] == admin_user.username
    assert member_client.post('/api/v1/approvals/', {'title': 'Request', 'content': 'Details',
        'assignee_username': 'adm'}, format='json').status_code == 400


def test_user_edit_payload_preserves_names(admin_client, member_user):
    member_user.first_name, member_user.last_name = 'Original', 'Name'
    member_user.save()
    row = next(row for row in admin_client.get('/api/v1/users/').json()['data']['items'] if row['id'] == str(member_user.pk))
    payload = {key: row[key] for key in ('first_name', 'last_name', 'is_active')}
    payload['email'] = 'updated@example.com'
    assert admin_client.patch(f'/api/v1/users/{member_user.pk}/', payload, format='json').status_code == 200
    member_user.refresh_from_db()
    assert (member_user.first_name, member_user.last_name) == ('Original', 'Name')


def test_create_disabled_user_cannot_login(admin_client):
    assert admin_client.post('/api/v1/users/', {'username': 'disabled', 'email': 'disabled@example.com',
        'password': 'Strong#12345', 'is_active': False}, format='json').status_code == 201
    assert APIClient().post('/api/v1/auth/login/', {'username': 'disabled', 'password': 'Strong#12345'}, format='json').status_code == 401


def test_export_does_not_emit_formula(admin_client, member_user):
    member_user.first_name = '=1+1'
    member_user.save()
    content = admin_client.get('/api/v1/data-io/export/?resource=users&export_format=xlsx').content
    workbook = load_workbook(io.BytesIO(content))
    cell = next(cell for row in workbook.active for cell in row if cell.value == "'=1+1")
    assert cell.data_type == 's'
    text = admin_client.get('/api/v1/data-io/export/?resource=users&export_format=csv').content.decode('utf-8-sig')
    assert "'=1+1" in next(row for row in csv.reader(io.StringIO(text)) if row[0] == 'member')


def test_raw_media_unavailable_and_download_obeys_soft_delete(member_client, settings):
    response = member_client.post('/api/v1/files/', {'file': SimpleUploadedFile('private.txt', b'private')}, format='multipart')
    file = FileModel.objects.get(pk=response.json()['id'])
    assert '/download/' in response.json()['file']
    assert APIClient().get(file.file.url).status_code == 404
    assert APIClient().get(f'/api/v1/files/{file.pk}/download/').status_code == 401
    assert member_client.delete(f'/api/v1/files/{file.pk}/').status_code == 204
    assert member_client.get(f'/api/v1/files/{file.pk}/download/').status_code == 404


def test_user_manager_cannot_modify_privileged_account(member_client, member_user, admin_user):
    permission = Permission.objects.create(name='Manage users', code='user:update', resource='user', action='update')
    role = Role.objects.create(name='User manager')
    RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=member_user, role=role)
    assert member_client.patch(f'/api/v1/users/{admin_user.pk}/', {'is_active': False}, format='json').status_code == 404
    assert member_client.post('/api/v1/users/bulk_action/', {
        'action': 'deactivate', 'user_ids': [str(admin_user.pk)],
    }, format='json').status_code == 200
    admin_user.refresh_from_db()
    assert admin_user.is_active
