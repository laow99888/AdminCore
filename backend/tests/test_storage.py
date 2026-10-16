"""存储配置和无本地路径后端的归档、失败回滚及迁移边界。"""
import io
import json
import tarfile

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage, Storage

from apps.core.media_storage import copy_exact, export_media, media_keys, restore_objects, save_state, storage_identity
from config.storage import storage_settings


class ObjectStorage(Storage):
    bucket_name = 'test-bucket'
    location = 'project/media'
    endpoint_url = 'https://storage.example.test'
    region_name = 'us-east-1'

    def __init__(self):
        self.inner = InMemoryStorage()

    def _open(self, name, mode='rb'):
        return self.inner.open(name, mode)

    def _save(self, name, content):
        return self.inner.save(name, content)

    def exists(self, name):
        return self.inner.exists(name)

    def delete(self, name):
        return self.inner.delete(name)

    def listdir(self, path):
        return self.inner.listdir(path)

    def size(self, name):
        return self.inner.size(name)

    def path(self, name):
        raise NotImplementedError('对象存储没有本地路径')


def configured(**values):
    return {'ADMINCORE_STORAGE_BACKEND': 's3', 'S3_BUCKET_NAME': 'private-bucket',
            'S3_ACCESS_KEY_ID': 'fixture-access', 'S3_SECRET_ACCESS_KEY': 'fixture-secret', **values}


def test_local_default_does_not_require_remote_credentials():
    assert storage_settings({})['default']['BACKEND'].endswith('FileSystemStorage')


def test_s3_private_signed_and_bounded_configuration():
    options = storage_settings(configured())['default']['OPTIONS']
    assert options['default_acl'] is None and options['querystring_auth']
    assert options['querystring_expire'] == 300 and not options['file_overwrite']
    assert options['client_config'].connect_timeout == 5
    assert options['client_config'].read_timeout == 30
    assert options['client_config'].signature_version == 's3v4'


@pytest.mark.parametrize('values', [
    {'S3_BUCKET_NAME': ''}, {'S3_ACCESS_KEY_ID': ''}, {'S3_SECRET_ACCESS_KEY': ''},
    {'S3_LOCATION': ''}, {'S3_LOCATION': 'a/../b'}, {'S3_LOCATION': 'a\\b'},
    {'S3_LOCATION': 'a//b'}, {'S3_LOCATION': 'a\nb'},
    {'S3_ENDPOINT_URL': 'http://localhost:9000'},
    {'S3_ENDPOINT_URL': 'https://user:pass@example.test'},
    {'S3_ENDPOINT_URL': 'https://example.test/bucket'},
    {'S3_ENDPOINT_URL': 'https://example.test?secret=value'},
    {'S3_ADDRESSING_STYLE': 'invalid'}, {'ADMINCORE_STORAGE_BACKEND': 'unknown'},
])
def test_invalid_config_fails_before_storage_operations(values):
    with pytest.raises(ImproperlyConfigured):
        storage_settings(configured(**values))


def test_explicit_development_http_is_supported():
    options = storage_settings(configured(S3_ENDPOINT_URL='http://127.0.0.1:18430',
                                         S3_ALLOW_INSECURE_HTTP='True'))['default']['OPTIONS']
    assert options['endpoint_url'] == 'http://127.0.0.1:18430'


def test_archive_uses_storage_interface_and_excludes_rollback_objects():
    storage = ObjectStorage()
    storage.save('uploads/中文.txt', ContentFile(b'payload'))
    storage.save('.admincore-restore-20261013-120000-123/old/private.txt', ContentFile(b'old'))
    output = io.BytesIO()
    export_media(storage, output)
    output.seek(0)
    with tarfile.open(fileobj=output, mode='r:gz') as archive:
        assert archive.getnames() == ['media/uploads/中文.txt']
        assert archive.extractfile(archive.getmembers()[0]).read() == b'payload'


def stage_restore(tmp_path, storage):
    stage = tmp_path / '.admincore-restore-20261013-120000-123'
    incoming = stage / 'new' / 'media' / 'uploads'
    incoming.mkdir(parents=True)
    (incoming / 'restored.txt').write_bytes(b'backup')
    save_state(stage, {'phase': 'prepared', 'old': [], 'new': [], 'storage': storage_identity(storage)})
    return stage


def test_object_commit_and_repeat_rollback_keep_old_bytes(tmp_path):
    storage = ObjectStorage()
    storage.save('uploads/current.txt', ContentFile(b'current'))
    stage = stage_restore(tmp_path, storage)
    restore_objects(storage, stage, 'commit')
    assert list(media_keys(storage)) == ['uploads/restored.txt']
    restore_objects(storage, stage, 'rollback')
    restore_objects(storage, stage, 'rollback')
    assert list(media_keys(storage)) == ['uploads/current.txt']
    assert storage.open('uploads/current.txt').read() == b'current'


def test_object_upload_failure_can_rollback(tmp_path, monkeypatch):
    storage = ObjectStorage()
    storage.save('uploads/current.txt', ContentFile(b'current'))
    stage = stage_restore(tmp_path, storage)
    original = storage.save

    def fail_new(name, *args, **kwargs):
        if name == 'uploads/restored.txt':
            raise OSError('fixture: remote unavailable')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(storage, 'save', fail_new)
    with pytest.raises(OSError):
        restore_objects(storage, stage, 'commit')
    restore_objects(storage, stage, 'rollback')
    assert storage.open('uploads/current.txt').read() == b'current'


def test_failed_old_backup_never_deletes_current(tmp_path, monkeypatch):
    storage = ObjectStorage()
    storage.save('uploads/current.txt', ContentFile(b'current'))
    stage = stage_restore(tmp_path, storage)
    monkeypatch.setattr(storage, 'save', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(OSError):
        restore_objects(storage, stage, 'commit')
    restore_objects(storage, stage, 'rollback')
    assert storage.open('uploads/current.txt').read() == b'current'


def test_changed_storage_identity_refuses_mutation(tmp_path):
    storage = ObjectStorage()
    stage = stage_restore(tmp_path, storage)
    storage.bucket_name = 'other-bucket'
    with pytest.raises(ValueError, match='配置已改变'):
        restore_objects(storage, stage, 'commit')
    assert json.loads((stage / 'state.json').read_text())['phase'] == 'prepared'


def test_copy_refuses_overwrite_and_keeps_source():
    source, destination = ObjectStorage(), ObjectStorage()
    source.save('uploads/file.txt', ContentFile(b'source'))
    destination.save('uploads/file.txt', ContentFile(b'different'))
    with pytest.raises(ValueError, match='拒绝覆盖'):
        copy_exact(source, 'uploads/file.txt', destination, 'uploads/file.txt')
    assert source.open('uploads/file.txt').read() == b'source'
    assert destination.open('uploads/file.txt').read() == b'different'


def test_backup_checksum_failure_never_deletes_original(tmp_path, monkeypatch):
    storage = ObjectStorage()
    storage.save('uploads/current.txt', ContentFile(b'original'))
    stage = stage_restore(tmp_path, storage)
    original_save = storage.save

    def corrupt(name, content, *args, **kwargs):
        return original_save(name, ContentFile(b'corrupt'), *args, **kwargs)

    monkeypatch.setattr(storage, 'save', corrupt)
    with pytest.raises(ValueError, match='校验失败'):
        restore_objects(storage, stage, 'commit')
    restore_objects(storage, stage, 'rollback')
    assert storage.open('uploads/current.txt').read() == b'original'


def test_corrupt_rollback_backup_refuses_to_delete_active_objects(tmp_path):
    storage = ObjectStorage()
    storage.save('uploads/current.txt', ContentFile(b'original'))
    stage = stage_restore(tmp_path, storage)
    restore_objects(storage, stage, 'commit')
    backup = stage.name + '/old/uploads/current.txt'
    storage.delete(backup)
    storage.save(backup, ContentFile(b'corrupt'))
    with pytest.raises(ValueError, match='校验失败'):
        restore_objects(storage, stage, 'rollback')
    assert storage.open('uploads/restored.txt').read() == b'backup'


def test_backup_rejects_local_symlink(tmp_path):
    from django.core.files.storage import FileSystemStorage
    outside = tmp_path / 'outside'
    outside.write_bytes(b'private')
    root = tmp_path / 'media'
    root.mkdir()
    try:
        (root / 'link').symlink_to(outside)
    except OSError:
        pytest.skip('当前 Windows 账户未获创建符号链接权限')
    with pytest.raises(ValueError, match='符号链接'):
        export_media(FileSystemStorage(location=root), io.BytesIO())


@pytest.mark.django_db
def test_remote_delete_failure_keeps_durable_intent(admin_user, monkeypatch):
    from datetime import timedelta
    from django.utils import timezone
    from apps.files.models import FileModel
    from apps.tasks.models import TaskRecord
    from apps.tasks.tasks import cleanup_soft_deleted_files

    record = FileModel.objects.create(uploader=admin_user, original_name='old.txt',
                                     file=ContentFile(b'old', name='old.txt'), size=3,
                                     is_deleted=True, deleted_at=timezone.now() - timedelta(days=100))
    storage = record.file.storage
    key = record.file.name
    monkeypatch.setattr(storage, 'delete', lambda *args: (_ for _ in ()).throw(OSError('fixture outage')))
    from apps.core.tasks import dispatch_outbox
    from apps.core.models import OutboxEvent
    assert cleanup_soft_deleted_files()['purged_files'] == 1
    assert dispatch_outbox()['failed'] == 1
    assert not FileModel.objects.filter(pk=record.pk).exists() and storage.exists(key)
    assert OutboxEvent.objects.filter(topic='file.purge', status='failed').exists()
    assert TaskRecord.objects.filter(task_type='cleanup', status='success').exists()
