"""文件与可靠事件的锁内授权、范围和上传补偿契约。"""
from unittest.mock import patch
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework.exceptions import AuthenticationFailed
from apps.files.models import FileModel
from apps.core.models import OutboxEvent
from apps.logs.models import OperationLog
from tests.file_permissions import grant_files

pytestmark = pytest.mark.django_db
User = get_user_model()


def file_for(user, deleted=False):
    row = FileModel.objects.create(original_name='fixture.txt', file_type='txt', size=7,
        uploader=user, file=SimpleUploadedFile('fixture.txt', b'fixture'))
    if deleted: row.soft_delete(actor=user)
    return row


def invoke(client, operation, row):
    base = f'/api/v1/files/{row.pk}/'
    if operation == 'upload': return client.post('/api/v1/files/', {'file': SimpleUploadedFile('new.txt', b'new')}, format='multipart')
    if operation == 'delete': return client.delete(base)
    if operation == 'restore': return client.post(base + 'restore/', {'lifecycle_version': row.lifecycle_version}, format='json')
    if operation == 'purge': return client.delete(base + 'purge/')
    if operation == 'download': return client.get(base + 'download/')
    if operation == 'preview': return client.get(base + 'preview/')
    return client.post('/api/v1/files/recycle_action/', {'action': 'restore', 'items': [{'id': str(row.pk), 'lifecycle_version': row.lifecycle_version}]}, format='json')


@pytest.mark.django_db(transaction=True)
def test_declared_upload_download_permissions_enforced(member_client, member_user, admin_user):
    row = file_for(member_user)
    for operation in ('upload', 'download', 'preview'):
        assert invoke(member_client, operation, row).status_code == 403
    grant_files(member_user, 'file:upload', 'file:download')
    assert invoke(member_client, 'upload', row).status_code == 201
    downloaded = invoke(member_client, 'download', row)
    assert downloaded.status_code == 200 and b''.join(downloaded.streaming_content) == b'fixture'
    downloaded.close()
    hidden = file_for(admin_user)
    assert invoke(member_client, 'download', hidden).status_code == 404
    assert invoke(member_client, 'preview', hidden).status_code == 404


@pytest.mark.parametrize('operation', ['upload', 'delete', 'restore', 'purge', 'recycle', 'download', 'preview'])
def test_original_jwt_device_rechecked_inside_file_transaction(admin_client, member_user, operation):
    row = file_for(member_user, operation in ('restore', 'recycle', 'purge'))
    before = FileModel.objects.count()
    with patch('apps.auth_app.sessions.locked_request_session', side_effect=AuthenticationFailed('revoked')) as check:
        response = invoke(admin_client, operation, row)
    if operation == 'recycle': assert response.json()['data']['results'][0]['status'] == 401
    else: assert response.status_code == 401
    check.assert_called_once()
    row.refresh_from_db()
    assert FileModel.objects.count() == before and row.file.storage.exists(row.file.name)
    assert not OperationLog.objects.filter(resource='file', resource_id=str(row.pk)).exists()


@pytest.mark.parametrize('operation', ['upload', 'delete', 'restore', 'purge', 'recycle', 'download', 'preview'])
def test_stale_disabled_actor_cannot_write_file(admin_user, member_user, operation):
    client = APIClient(); client.force_authenticate(admin_user)
    row = file_for(member_user, operation in ('restore', 'recycle', 'purge'))
    User.objects.filter(pk=admin_user.pk).update(is_active=False)
    response = invoke(client, operation, row)
    if operation == 'recycle': assert response.json()['data']['results'][0]['status'] == 401
    else: assert response.status_code == 401
    assert FileModel.objects.filter(pk=row.pk).exists()


def test_upload_audit_failure_rolls_back_row_and_only_removes_new_key(admin_client, admin_user):
    original = file_for(admin_user)
    storage = original.file.storage
    old_key = original.file.name
    admin_client.raise_request_exception = False
    with patch('apps.files.views.FileViewSet._log', side_effect=RuntimeError('audit down')), patch.object(storage, 'delete', wraps=storage.delete) as remove:
        response = invoke(admin_client, 'upload', original)
    assert response.status_code == 500 and FileModel.objects.count() == 1
    assert storage.exists(old_key)
    remove.assert_called_once()
    assert remove.call_args.args[0] != old_key and not storage.exists(remove.call_args.args[0])


def test_upload_database_failure_removes_committed_new_blob(admin_client, admin_user):
    from django.db import connection
    row = file_for(admin_user); storage = row.file.storage
    admin_client.raise_request_exception = False
    def fail_insert(execute, sql, params, many, context):
        if sql.startswith('INSERT INTO "files_filemodel"'):
            # FileField.pre_save has already committed the new blob before SQL is sent.
            raise RuntimeError('database insert unavailable after storage commit')
        return execute(sql, params, many, context)
    deleted_keys = []
    original_delete = storage.delete
    def remove_new(key):
        assert key != row.file.name and storage.exists(key)
        deleted_keys.append(key); return original_delete(key)
    with connection.execute_wrapper(fail_insert), patch.object(storage, 'delete', side_effect=remove_new):
        response = invoke(admin_client, 'upload', row)
    assert response.status_code == 500 and storage.exists(row.file.name) and FileModel.objects.count() == 1
    assert len(deleted_keys) == 1 and not storage.exists(deleted_keys[0])


def test_outbox_retry_requires_fresh_admin_and_original_device(admin_user, admin_client):
    event = OutboxEvent.objects.create(topic='notification.created', event_key='fresh-auth', payload={}, status='failed', available_at=timezone.now())
    url = f'/api/v1/reliability/events/{event.pk}/retry/'
    with patch('apps.auth_app.sessions.locked_request_session', side_effect=AuthenticationFailed('revoked')):
        assert admin_client.post(url).status_code == 401
    stale = APIClient(); stale.force_authenticate(admin_user)
    User.objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    assert stale.post(url).status_code == 403
    event.refresh_from_db()
    assert event.status == 'failed' and not OperationLog.objects.filter(resource='outbox_event').exists()


@pytest.mark.parametrize('operation', ['delete', 'restore', 'download', 'preview'])
def test_target_scope_recomputed_after_stale_admin_downgraded(admin_user, member_user, operation):
    client = APIClient(); client.force_authenticate(admin_user)
    grant_files(admin_user, 'file:download', 'file:restore')
    row = file_for(member_user, operation == 'restore')
    User.objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    response = invoke(client, operation, row)
    assert response.status_code == 404
    row.refresh_from_db()
    assert row.is_deleted == (operation == 'restore') and row.file.storage.exists(row.file.name)


def test_immutable_file_metadata_has_no_empty_put_patch_write(admin_client, admin_user):
    row = file_for(admin_user)
    for method in ('put', 'patch'):
        result = getattr(admin_client, method)(f'/api/v1/files/{row.pk}/', {'description': 'discard'}, format='json')
        assert result.status_code == 405
    row.refresh_from_db()
    assert row.description == '' and row.lifecycle_version == 1
