"""由 validate_storage.py 对独立的真实 MinIO 实例运行，常规 pytest 不运行。"""
import importlib.util
import io
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import boto3
import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from django.test import override_settings
from django.utils import timezone

from apps.core.media_storage import copy_exact, export_media, media_keys
from apps.files.models import FileModel
from config.storage import storage_settings

pytest_plugins = ['tests.conftest']
pytestmark = pytest.mark.django_db


def test_real_s3_bounded_image_transformation(s3_storage, admin_client, member_client):
    from tests.test_image_processing import upload, picture, process, stream
    from PIL import Image
    original = picture(metadata=True)
    with override_settings(ADMINCORE_IMAGE_PROCESSING_ENABLED=True):
        row = upload(admin_client, original)
        keys = list(media_keys(s3_storage))
        for format in ['png', 'jpeg', 'webp']:
            response = process(admin_client, row, width=80, height=80, format=format,
                               watermark=stream(picture((20, 20), color='red')))
            assert response.status_code == 200 and response['Content-Type'] == 'image/' + format
            with Image.open(io.BytesIO(response.content)) as image:
                assert image.size == (80, 53) and not image.getexif()
            assert response['Cache-Control'] == 'private, no-store'
        assert list(media_keys(s3_storage)) == keys
        with row.file.open('rb') as source:
            assert source.read() == original
        assert process(member_client, row).status_code == 403
        unsigned = s3_storage.url(row.file.name).split('?')[0]
        with pytest.raises(urllib.error.HTTPError) as private:
            urllib.request.urlopen(unsigned)
        assert private.value.code == 403


def test_real_s3_import_source_retention(s3_storage, admin_user):
    from datetime import timedelta
    from apps.tasks.lifecycle import clean
    from apps.tasks.models import TaskRecord
    row = FileModel.objects.create(original_name='import.csv', file=ContentFile(b'username\nu1', name='import.csv'),
                                   uploader=admin_user, purpose='import', size=11)
    FileModel.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=400))
    task = TaskRecord.objects.create(name='导入', task_type='import', status='pending', result={'file_id': str(row.pk)})
    assert clean()['protected_imports'] == 1 and s3_storage.exists(row.file.name)
    task.status = 'failed'
    task.completed_at = timezone.now() - timedelta(days=100)
    task.save()
    assert clean(dry_run=True)['eligible']['imports'] == 1 and s3_storage.exists(row.file.name)
    assert clean()['deleted']['imports'] == 1
    assert not s3_storage.exists(row.file.name) and not FileModel.objects.filter(pk=row.pk).exists()


def test_real_s3_private_profile_avatar_lifecycle(s3_storage, member_client, member_user, admin_client):
    from datetime import timedelta
    from PIL import Image
    from tests.test_personal_profile import upload, AVATAR
    from apps.tasks.tasks import cleanup_soft_deleted_files
    assert upload(member_client).status_code == 200
    member_user.refresh_from_db()
    old = member_user.avatar_file
    with Image.open(io.BytesIO(member_client.get(AVATAR).content)) as image:
        assert image.size == (256, 256) and image.format == 'PNG'
    assert admin_client.get(AVATAR).status_code == 404
    assert admin_client.get(f'/api/v1/files/{old.pk}/download/').status_code == 404
    unsigned = s3_storage.url(old.file.name).split('?')[0]
    with pytest.raises(urllib.error.HTTPError) as private:
        urllib.request.urlopen(unsigned)
    assert private.value.code == 403
    assert old.file.name in media_keys(s3_storage)
    assert upload(member_client, 2).status_code == 200
    assert member_client.delete(AVATAR, {'profile_version': 3}, format='json').status_code == 200
    assert s3_storage.exists(old.file.name)
    FileModel.objects.filter(purpose='avatar').update(deleted_at=timezone.now() - timedelta(days=40))
    assert cleanup_soft_deleted_files()['purged_files'] == 2
    assert not s3_storage.exists(old.file.name) and not FileModel.objects.exists()


def test_real_s3_authenticated_image_and_pdf_preview(s3_storage, admin_client, member_client):
    from tests.test_file_preview import image_bytes, pdf_bytes, upload, preview
    for name, content, mime in [('private.png', image_bytes(), 'image/png'),
                                ('private.pdf', pdf_bytes(), 'application/pdf')]:
        id = upload(admin_client, name, content)
        result = preview(admin_client, id)
        assert result.status_code == 200 and result['Content-Type'] == mime
        assert result['Cache-Control'] == 'private, no-store'
        assert preview(member_client, id).status_code == 404
        assert admin_client.delete(f'/api/v1/files/{id}/').status_code == 204
        assert preview(admin_client, id).status_code == 404
        assert admin_client.post(f'/api/v1/files/{id}/restore/', {'lifecycle_version': 2}, format='json').status_code == 200
        assert preview(admin_client, id).status_code == 200


@pytest.fixture
def s3_storage():
    endpoint = os.environ['STORAGE_CONTRACT_ENDPOINT']
    environment = {'ADMINCORE_STORAGE_BACKEND': 's3', 'S3_ENDPOINT_URL': endpoint,
                   'S3_ALLOW_INSECURE_HTTP': 'True', 'S3_BUCKET_NAME': 'admincore-fixture',
                   'S3_LOCATION': 'isolated-media', 'S3_ACCESS_KEY_ID': os.environ['STORAGE_CONTRACT_ACCESS'],
                   'S3_SECRET_ACCESS_KEY': os.environ['STORAGE_CONTRACT_SECRET']}
    client = boto3.client('s3', endpoint_url=endpoint, region_name='us-east-1',
                          aws_access_key_id=environment['S3_ACCESS_KEY_ID'],
                          aws_secret_access_key=environment['S3_SECRET_ACCESS_KEY'])
    client.create_bucket(Bucket=environment['S3_BUCKET_NAME'])
    with override_settings(STORAGES=storage_settings(environment)):
        yield default_storage
    # 仅清理本 fixture 的固定桶，进程结束前验证没有泄露活动对象。
    objects = client.list_objects_v2(Bucket=environment['S3_BUCKET_NAME']).get('Contents', [])
    if objects:
        client.delete_objects(Bucket=environment['S3_BUCKET_NAME'],
                              Delete={'Objects': [{'Key': item['Key']} for item in objects]})
    client.delete_bucket(Bucket=environment['S3_BUCKET_NAME'])


def test_real_s3_upload_authorization_cleanup_backup_restore(s3_storage, admin_client, member_client, tmp_path, monkeypatch):
    storage = s3_storage
    upload = io.BytesIO(b'actual-s3-file')
    upload.name = 'private.txt'
    response = admin_client.post('/api/v1/files/', {'file': upload}, format='multipart')
    assert response.status_code == 201
    record = FileModel.objects.get(pk=response.json()['id'])
    assert '\\' not in record.file.name
    assert storage.open(record.file.name).read() == b'actual-s3-file'
    assert '/download/' in response.json()['file'] and 'X-Amz' not in json.dumps(response.json())
    download = f'/api/v1/files/{record.pk}/download/'
    assert member_client.get(download).status_code == 404
    from rest_framework.test import APIClient
    assert APIClient().get(download).status_code == 401
    result = admin_client.get(download)
    assert result.status_code == 200 and b''.join(result.streaming_content) == b'actual-s3-file'
    result.close()
    signed = storage.url(record.file.name, expire=1)
    unsigned = signed.split('?')[0]
    with pytest.raises(urllib.error.HTTPError) as private:
        urllib.request.urlopen(unsigned)
    assert private.value.code == 403
    with urllib.request.urlopen(signed) as valid:
        assert valid.read() == b'actual-s3-file'
    time.sleep(2)
    with pytest.raises(urllib.error.HTTPError) as expired:
        urllib.request.urlopen(signed)
    assert expired.value.code == 403
    # 两种后端复制保留原对象键，SHA-256 校验，源文件仍可访问。
    local = FileSystemStorage(location=tmp_path / 'copy')
    copy_exact(storage, record.file.name, local, record.file.name)
    assert local.open(record.file.name).read() == b'actual-s3-file'
    extra = local.save('uploads/from-local.txt', ContentFile(b'local-to-s3'))
    copy_exact(local, extra, storage, extra)
    # 用正式归档/恢复入口验收保留对象键和回滚，而非仅重写一份对象。
    archive = io.BytesIO()
    export_media(storage, archive)
    archive.seek(0)
    spec = importlib.util.spec_from_file_location('media_restore', Path(__file__).resolve().parents[1] / 'docker/media_restore.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'MEDIA', tmp_path / 'stage')
    monkeypatch.setattr(module, 'object_storage', lambda: storage)
    monkeypatch.setattr(module.sys, 'stdin', SimpleNamespace(buffer=archive))
    token = '20261013-120000-123'
    module.main('prepare', token)
    storage.delete(record.file.name)
    storage.save('uploads/current-only.txt', ContentFile(b'current'))
    current = list(media_keys(storage))
    module.main('commit', token)
    assert storage.open(record.file.name).read() == b'actual-s3-file'
    assert not storage.exists('uploads/current-only.txt')
    module.main('rollback', token)
    assert list(media_keys(storage)) == current
    assert storage.open('uploads/current-only.txt').read() == b'current'
    # 清理任务真正删除对象；失败处理由针对性单元测试验证。
    storage.save(record.file.name, ContentFile(b'actual-s3-file'))
    assert admin_client.delete(f'/api/v1/files/{record.pk}/').status_code == 204
    record.refresh_from_db()
    key = record.file.name
    assert admin_client.post(f'/api/v1/files/{record.pk}/restore/', {
        'lifecycle_version': record.lifecycle_version,
    }, format='json').status_code == 200
    record.refresh_from_db()
    assert not record.is_deleted and record.file.name == key
    assert storage.open(key).read() == b'actual-s3-file'
    assert member_client.get(download).status_code == 404
    assert admin_client.delete(f'/api/v1/files/{record.pk}/').status_code == 204
    record.refresh_from_db()
    assert cleanup_soft_deleted_files_preview(admin_client, record)['succeeded'] == 1
    record.deleted_at = timezone.now() - timezone.timedelta(days=100)
    record.save(update_fields=['deleted_at'])
    from apps.tasks.tasks import cleanup_soft_deleted_files
    cleanup_soft_deleted_files()
    assert not FileModel.objects.filter(pk=record.pk).exists()
    assert not storage.exists(record.file.name)


def cleanup_soft_deleted_files_preview(client, record):
    result = client.post('/api/v1/files/recycle_action/', {
        'action': 'purge', 'dry_run': True,
        'items': [{'id': str(record.pk), 'lifecycle_version': record.lifecycle_version}],
    }, format='json')
    assert result.status_code == 200
    return result.json()['data']


def test_real_s3_recycle_missing_file_and_permanent_delete(s3_storage, admin_client):
    upload = io.BytesIO(b'recycle-fixture')
    upload.name = 'trash.txt'
    uploaded = admin_client.post('/api/v1/files/', {'file': upload}, format='multipart').json()
    record = FileModel.objects.get(pk=uploaded['id'])
    admin_client.delete(f'/api/v1/files/{record.pk}/')
    record.refresh_from_db()
    key = record.file.name
    s3_storage.delete(key)
    assert admin_client.post(f'/api/v1/files/{record.pk}/restore/', {'lifecycle_version': 2}, format='json').status_code == 409
    s3_storage.save(key, ContentFile(b'recycle-fixture'))
    result = admin_client.post('/api/v1/files/recycle_action/', {
        'action': 'purge', 'confirmation': 'DELETE',
        'items': [{'id': str(record.pk), 'lifecycle_version': 2}],
    }, format='json')
    assert result.json()['data']['succeeded'] == 1
    assert not FileModel.objects.filter(pk=record.pk).exists() and not s3_storage.exists(key)


def test_real_s3_import_and_copy_command(s3_storage, admin_client, tmp_path, monkeypatch):
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from openpyxl import Workbook
    from apps.tasks.models import TaskRecord

    workbook = Workbook()
    workbook.active.append(['username', 'email', 'first_name', 'last_name', 'phone'])
    workbook.active.append(['s3-import-user', 's3-import@example.test', '', '', ''])
    uploaded = io.BytesIO()
    workbook.save(uploaded)
    uploaded.seek(0)
    uploaded.name = 'users.xlsx'
    response = admin_client.post('/api/v1/data-io/import/',
                                 {'file': uploaded, 'resource': 'users'}, format='multipart')
    assert response.status_code == 200
    task = TaskRecord.objects.get(pk=response.json()['data']['id'])
    assert task.status == 'pending' and task.import_execution.batch.source_sha256
    from apps.data_io.tasks import run_data_import
    run_data_import(str(task.pk))
    task.refresh_from_db()
    assert task.status == 'success' and task.result['created'] == 1
    assert get_user_model().objects.filter(username='s3-import-user').exists()
    record = FileModel.objects.get(pk=task.result['file_id'])
    assert s3_storage.exists(record.file.name)
    for name, value in {
        'S3_ENDPOINT_URL': os.environ['STORAGE_CONTRACT_ENDPOINT'],
        'S3_ACCESS_KEY_ID': os.environ['STORAGE_CONTRACT_ACCESS'],
        'S3_SECRET_ACCESS_KEY': os.environ['STORAGE_CONTRACT_SECRET'],
        'S3_BUCKET_NAME': 'admincore-fixture', 'S3_LOCATION': 'isolated-media',
        'S3_ALLOW_INSECURE_HTTP': 'True',
    }.items():
        monkeypatch.setenv(name, value)
    local_root = tmp_path / 'migration'
    local_root.mkdir()
    local = FileSystemStorage(location=local_root)
    local.save('uploads/migrated.txt', ContentFile(b'persisted-key'))
    with override_settings(MEDIA_ROOT=local_root):
        call_command('copy_media', source='local', destination='s3', stdout=io.StringIO())
        assert not s3_storage.exists('uploads/migrated.txt')
        call_command('copy_media', source='local', destination='s3', execute=True, stdout=io.StringIO())
        call_command('copy_media', source='local', destination='s3', execute=True, stdout=io.StringIO())
        assert local.open('uploads/migrated.txt').read() == b'persisted-key'
        assert s3_storage.open('uploads/migrated.txt').read() == b'persisted-key'
        s3_storage.delete('uploads/migrated.txt')
        s3_storage.save('uploads/migrated.txt', ContentFile(b'conflict'))
        with pytest.raises(CommandError, match='拒绝覆盖'):
            call_command('copy_media', source='local', destination='s3', execute=True, stdout=io.StringIO())
        assert local.open('uploads/migrated.txt').read() == b'persisted-key'
