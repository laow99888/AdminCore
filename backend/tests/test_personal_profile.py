"""本人资料、私有头像和存储故障的隔离回归测试。"""
import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from PIL import Image, PngImagePlugin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.core.models import LifecycleConflict
from apps.files.models import FileModel, FileStorageError
from apps.logs.models import OperationLog
from apps.tasks.tasks import cleanup_soft_deleted_files

pytestmark = pytest.mark.django_db
PROFILE = '/api/v1/auth/profile/'
AVATAR = '/api/v1/auth/avatar/'


def image_upload(name='picture.png', kind='PNG', size=(320, 180)):
    output = io.BytesIO()
    image = Image.new('RGB', size, 'blue')
    info = PngImagePlugin.PngInfo()
    info.add_text('Comment', 'private metadata')
    image.save(output, kind, **({'pnginfo': info} if kind == 'PNG' else {}))
    return SimpleUploadedFile(name, output.getvalue(), content_type='image/' + kind.lower())


def upload(client, version=1):
    return client.post(AVATAR, {'file': image_upload(), 'profile_version': version}, format='multipart')


def test_self_profile_update_and_audit(member_client, member_user, admin_user):
    snapshot = member_client.get(PROFILE).json()['data']
    assert snapshot['bio'] == '' and snapshot['profile_version'] == 1
    response = member_client.patch(PROFILE, {'profile_version': 1, 'first_name': '姓名', 'last_name': '姓',
                                             'phone': '+86 12345678', 'email': 'new@example.com', 'bio': '个人简介'}, format='json')
    assert response.status_code == 200
    data = response.json()['data']
    assert data['first_name'] == '姓名' and data['bio'] == '个人简介' and data['profile_version'] == 2
    admin_user.refresh_from_db()
    assert admin_user.email == 'admin@example.com'
    description = OperationLog.objects.get(resource='profile').description
    assert 'bio' in description and 'new@example.com' not in description and '个人简介' not in description
    assert member_client.get('/api/v1/auth/me/').json()['data']['profile_version'] == 2


@pytest.mark.parametrize('field,value', [('id', 'other'), ('username', 'other'), ('is_superuser', True),
    ('is_active', False), ('permissions', ['*']), ('password', 'Compromised#123'), ('must_change_password', False),
    ('avatar_file', 'other'), ('avatar', 'https://example.com/image.png')])
def test_forbidden_fields_reject_entire_write(member_client, member_user, field, value):
    assert member_client.patch(PROFILE, {'profile_version': 1, 'first_name': 'discard', field: value}, format='json').status_code == 400
    member_user.refresh_from_db()
    assert member_user.first_name == '' and member_user.profile_version == 1


@pytest.mark.parametrize('payload', [{}, {'profile_version': 0}, {'profile_version': 1, 'email': 'invalid'},
    {'profile_version': 1, 'phone': 'abc'}, {'profile_version': 1, 'bio': 'a' * 1001}])
def test_validation(member_client, payload):
    assert member_client.patch(PROFILE, payload, format='json').status_code == 400


@pytest.mark.parametrize('payload', [[], [{}], True, 'invalid', None], ids=['list', 'nested-list', 'boolean', 'string', 'null'])
def test_non_object_payload_returns_validation_error(member_client, payload):
    assert member_client.patch(PROFILE, payload, format='json').status_code == 400


def test_old_version_preserves_latest_and_admin_edits_invalidate(member_client, admin_client, member_user):
    assert member_client.patch(PROFILE, {'profile_version': 1, 'bio': 'new'}, format='json').status_code == 200
    assert member_client.patch(PROFILE, {'profile_version': 1, 'bio': 'stale'}, format='json').status_code == 409
    assert admin_client.patch(f'/api/v1/users/{member_user.pk}/', {'email': 'admin-edit@example.com'}, format='json').status_code == 200
    assert member_client.patch(PROFILE, {'profile_version': 2, 'email': 'stale@example.com'}, format='json').status_code == 409
    assert member_client.get(PROFILE).json()['data']['bio'] == 'new'


@pytest.mark.parametrize('method,path', [('get', PROFILE), ('patch', PROFILE), ('get', AVATAR), ('post', AVATAR), ('delete', AVATAR)])
def test_requires_authenticated_unrestricted_account(member_client, member_user, method, path):
    assert getattr(APIClient(), method)(path).status_code == 401
    member_user.must_change_password = True
    member_user.save()
    assert getattr(member_client, method)(path).status_code == 403


def test_avatar_private_normalized_and_hidden_from_general_files(member_client, member_user, admin_client):
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    asset = member_user.avatar_file
    assert asset.purpose == 'avatar' and not asset.is_deleted
    with asset.file.open('rb') as source:
        with Image.open(source) as image:
            assert image.format == 'PNG' and image.size == (256, 256) and 'Comment' not in image.info
    response = member_client.get(AVATAR)
    assert response.status_code == 200 and response['Content-Type'] == 'image/png'
    assert response['Cache-Control'] == 'private, no-store' and response['X-Content-Type-Options'] == 'nosniff'
    assert admin_client.get(AVATAR).status_code == 404
    for client in [member_client, admin_client]:
        assert client.get(f'/api/v1/files/{asset.pk}/').status_code == 404
        assert client.get(f'/api/v1/files/{asset.pk}/download/').status_code == 404
        assert client.get('/api/v1/files/').json()['data']['pagination']['total'] == 0
    assert admin_client.get('/api/v1/dashboard/stats/').json()['data']['totals']['files'] == 0
    with pytest.raises(LifecycleConflict):
        asset.hard_delete()
    assert asset.file.storage.exists(asset.file.name)


@pytest.mark.parametrize('name,kind', [('wrong.jpg', 'PNG'), ('vector.svg', 'PNG')])
def test_avatar_format_mismatch(member_client, name, kind):
    assert member_client.post(AVATAR, {'file': image_upload(name, kind), 'profile_version': 1}, format='multipart').status_code == 400
    assert FileModel.objects.count() == 0


@pytest.mark.parametrize('content', [b'', b'not an image', b'a' * (5 * 1024 * 1024 + 1)], ids=['empty', 'corrupt', 'oversize'])
def test_avatar_invalid_bytes_and_size(member_client, content):
    file = SimpleUploadedFile('file.png', content)
    assert member_client.post(AVATAR, {'file': file, 'profile_version': 1}, format='multipart').status_code == 400
    assert FileModel.objects.count() == 0


def test_avatar_pixel_limit(member_client):
    assert member_client.post(AVATAR, {'file': image_upload(size=(2001, 2000)), 'profile_version': 1}, format='multipart').status_code == 400


@pytest.mark.parametrize('name,kind', [('photo.jpg', 'JPEG'), ('photo.webp', 'WEBP')])
def test_supported_formats_are_normalized(member_client, name, kind):
    response = member_client.post(AVATAR, {'file': image_upload(name, kind), 'profile_version': 1}, format='multipart')
    assert response.status_code == 200
    with Image.open(io.BytesIO(member_client.get(AVATAR).content)) as image:
        assert image.format == 'PNG' and image.size == (256, 256)


def test_avatar_admin_generic_editor_cannot_access(member_client, member_user, admin_user):
    from django.test import Client
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    client = Client()
    client.force_login(admin_user)
    response = client.get(f'/admin/files/filemodel/{member_user.avatar_file_id}/change/')
    assert response.status_code == 302 and response.url == '/admin/'


def test_binding_failure_cleans_staging_and_keeps_previous_avatar(member_client, member_user):
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    old_id = member_user.avatar_file_id
    with patch('apps.auth_app.profile.audit', side_effect=RuntimeError('binding failed')):
        assert upload(member_client, 2).status_code == 503
    member_user.refresh_from_db()
    assert member_user.profile_version == 2 and member_user.avatar_file_id == old_id
    assert FileModel.objects.count() == 1 and not member_user.avatar_file.is_deleted


def test_replace_remove_retire_and_cleanup(member_client, member_user):
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    old = member_user.avatar_file
    assert upload(member_client, 2).status_code == 200
    old.refresh_from_db()
    assert old.is_deleted and old.deleted_at and old.file.storage.exists(old.file.name)
    with pytest.raises(LifecycleConflict):
        old.restore(old.lifecycle_version)
    assert member_client.delete(AVATAR, {'profile_version': 2}, format='json').status_code == 409
    assert member_client.delete(AVATAR, {'profile_version': 3}, format='json').status_code == 200
    assert member_client.get(AVATAR).status_code == 404
    FileModel.objects.update(deleted_at=timezone.now() - timedelta(days=40))
    assert cleanup_soft_deleted_files(dry_run=True)['eligible_files'] == 2
    assert cleanup_soft_deleted_files()['purged_files'] == 2
    assert not FileModel.objects.exists() and not old.file.storage.exists(old.file.name)


def test_minimal_profile_available_avatar_disabled(member_client):
    with override_settings(ADMINCORE_MODULES=()):
        assert member_client.get(PROFILE).json()['data']['avatar_enabled'] is False
        assert member_client.patch(PROFILE, {'profile_version': 1, 'bio': 'minimal'}, format='json').status_code == 200
        for method in ['get', 'post', 'delete']:
            assert getattr(member_client, method)(AVATAR).status_code == 404


def test_user_deletion_retires_owned_avatar(member_client, member_user):
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    asset = member_user.avatar_file
    member_user.delete()
    asset.refresh_from_db()
    assert asset.is_deleted and asset.uploader_id is None
    FileModel.objects.filter(pk=asset.pk).update(deleted_at=timezone.now() - timedelta(days=40))
    assert cleanup_soft_deleted_files()['purged_files'] == 1


def test_stale_avatar_upload_compensates_without_retiring_current(member_client, member_user):
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    current = member_user.avatar_file
    assert upload(member_client).status_code == 409
    assert FileModel.objects.count() == 1
    current.refresh_from_db()
    assert not current.is_deleted


def test_storage_failure_sanitized_and_pending_cleanup_retained(member_client):
    storage = FileModel._meta.get_field('file').storage
    with patch.object(storage, 'save', side_effect=OSError('secret-access-key')):
        with patch.object(storage, 'delete', side_effect=OSError('secret-access-key')):
            response = upload(member_client)
    assert response.status_code == 503 and 'secret-access-key' not in response.content.decode()
    asset = FileModel.objects.get()
    assert asset.is_deleted and asset.deleted_at and not asset.avatar_users.exists()
    FileModel.objects.filter(pk=asset.pk).update(deleted_at=timezone.now() - timedelta(days=40))
    assert cleanup_soft_deleted_files()['purged_files'] == 1


def test_read_storage_failure_sanitized(member_client):
    assert upload(member_client).status_code == 200
    storage = FileModel._meta.get_field('file').storage
    with patch.object(storage, 'open', side_effect=OSError('secret-signature')):
        response = member_client.get(AVATAR)
    assert response.status_code == 503 and 'secret-signature' not in response.content.decode()


def test_retention_storage_failure_keeps_record(member_client, member_user):
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    asset = member_user.avatar_file
    assert member_client.delete(AVATAR, {'profile_version': 2}, format='json').status_code == 200
    FileModel.objects.filter(pk=asset.pk).update(deleted_at=timezone.now() - timedelta(days=40))
    with patch.object(asset.file.storage, 'delete', side_effect=OSError('unavailable')):
        with pytest.raises(FileStorageError):
            cleanup_soft_deleted_files()
    assert FileModel.objects.filter(pk=asset.pk, is_deleted=True).exists()
    assert cleanup_soft_deleted_files()['purged_files'] == 1


def test_password_reset_during_upload_prevents_binding(member_client, member_user):
    from django.contrib.auth import get_user_model
    storage = FileModel._meta.get_field('file').storage
    save = storage.save
    def reset_then_save(*args, **kwargs):
        get_user_model().objects.filter(pk=member_user.pk).update(session_version=1)
        return save(*args, **kwargs)
    with patch.object(storage, 'save', side_effect=reset_then_save):
        assert upload(member_client).status_code == 401
    member_user.refresh_from_db()
    assert member_user.avatar_file_id is None and FileModel.objects.count() == 0


def test_django_admin_preserves_current_binding_and_bumps_version(member_client, member_user):
    from types import SimpleNamespace
    from django.contrib import admin
    from apps.auth_app.admin import UserAdmin
    from django.contrib.auth import get_user_model
    stale = get_user_model().objects.get(pk=member_user.pk)
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    stale.email = 'edited@example.com'
    request = SimpleNamespace()
    UserAdmin(type(stale), admin.site).save_model(request, stale, SimpleNamespace(changed_data=['email']), True)
    assert request._admin_audit_before[(stale._meta.label, str(stale.pk))]['profile_version'] == 2
    member_user.refresh_from_db()
    assert member_user.avatar_file_id == stale.avatar_file_id and member_user.profile_version == 3


def test_stale_user_deletion_retires_latest_binding(member_client, member_user):
    assert member_user.avatar_file_id is None
    assert upload(member_client).status_code == 200
    avatar = FileModel.objects.get(purpose='avatar')
    member_user.delete()  # 故意使用上传前的实例。
    avatar.refresh_from_db()
    assert avatar.is_deleted and avatar.uploader_id is None


def test_deleted_user_during_upload_cannot_bind(member_client, member_user):
    storage = FileModel._meta.get_field('file').storage
    save = storage.save
    def delete_then_save(*args, **kwargs):
        member_user.delete()
        return save(*args, **kwargs)
    with patch.object(storage, 'save', side_effect=delete_then_save):
        assert upload(member_client).status_code == 401
    assert not FileModel.objects.exists()
