import hashlib
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.files.models import ResumableUpload
from apps.files.resumable import cleanup_expired_sessions

pytestmark = pytest.mark.django_db


def start(client):
    result = client.post('/api/v1/files/uploads/', {
        'name': 'recovery.txt', 'total_size': 3, 'chunk_size': 262144,
    }, format='json')
    assert result.status_code == 201
    return ResumableUpload.objects.get(pk=result.data['data']['id'])


def put(client, row, body):
    return client.put(f'/api/v1/files/uploads/{row.pk}/chunks/0/', body,
        content_type='application/octet-stream', HTTP_X_CHUNK_SHA256=hashlib.sha256(body).hexdigest())


def test_chunk_database_failure_can_retry_different_content(admin_client, monkeypatch):
    row = start(admin_client)
    original = ResumableUpload.save
    failed = []

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') == ['chunks', 'updated_at'] and not failed:
            failed.append(True)
            raise RuntimeError('injected database failure')
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ResumableUpload, 'save', save)
    assert put(admin_client, row, b'old').status_code == 500
    row.refresh_from_db()
    assert row.chunks == {}
    assert put(admin_client, row, b'new').status_code == 200
    result = admin_client.post(f'/api/v1/files/uploads/{row.pk}/complete/')
    assert result.status_code == 200, result.data
    row.refresh_from_db()
    with row.file.file.open('rb') as stream:
        assert stream.read() == b'new'
    assert row.chunks_cleaned


@pytest.mark.parametrize('completed', [False, True])
def test_chunk_cleanup_retries_after_storage_recovers(admin_client, monkeypatch, completed):
    row = start(admin_client)
    assert put(admin_client, row, b'new').status_code == 200
    row.refresh_from_db()
    name = row.chunks['0']['name']
    real_delete = default_storage.delete
    monkeypatch.setattr(default_storage, 'delete', lambda key: (_ for _ in ()).throw(OSError('storage outage')))
    if completed:
        assert admin_client.post(f'/api/v1/files/uploads/{row.pk}/complete/').status_code == 200
    else:
        ResumableUpload.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        assert cleanup_expired_sessions() == 0
    row.refresh_from_db()
    assert not row.chunks_cleaned and default_storage.exists(name)
    monkeypatch.setattr(default_storage, 'delete', real_delete)
    assert cleanup_expired_sessions() == 1
    row.refresh_from_db()
    assert row.chunks_cleaned and not default_storage.exists(name)
    assert cleanup_expired_sessions() == 0


def test_legacy_terminal_session_cleans_unrecorded_objects_only_in_its_directory(admin_client):
    old = start(admin_client)
    active = start(admin_client)
    orphan = default_storage.save(f'uploads/.chunks/{old.pk}/0_legacy.part', ContentFile(b'old'))
    other = default_storage.save(f'uploads/.chunks/{active.pk}/0.part', ContentFile(b'new'))
    ResumableUpload.objects.filter(pk=old.pk).update(status='completed')
    assert cleanup_expired_sessions() == 1
    assert not default_storage.exists(orphan)
    assert default_storage.exists(other)
