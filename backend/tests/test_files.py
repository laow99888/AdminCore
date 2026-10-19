"""
文件管理测试
"""

import io
import hashlib
from datetime import timedelta

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings
from django.utils import timezone

from tests.file_permissions import grant_files
from apps.files.models import FileModel, ResumableUpload


def make_file(name='test.txt', content=b'hello admincore'):
    f = io.BytesIO(content)
    f.name = name
    return f


class TestUpload:
    def test_upload_txt_success(self, admin_client):
        res = admin_client.post('/api/v1/files/', {'file': make_file()}, format='multipart')
        assert res.status_code == 201
        data = res.json()
        assert data['original_name'] == 'test.txt'
        assert data['file_type'] == 'txt'
        assert data['size'] == len(b'hello admincore')

    def test_upload_exe_rejected_by_whitelist(self, admin_client):
        res = admin_client.post('/api/v1/files/', {'file': make_file('bad.exe', b'xx')}, format='multipart')
        assert res.status_code == 400

    def test_resumable_upload_round_trip(self, admin_client):
        content = b'A' * (256 * 1024) + b'B' * 1024
        chunk_size = 256 * 1024
        start = admin_client.post('/api/v1/files/uploads/', {
            'name': 'resume.txt', 'total_size': len(content), 'chunk_size': chunk_size,
            'content_type': 'text/plain', 'sha256': hashlib.sha256(content).hexdigest(),
        }, format='json')
        assert start.status_code == 201, start.content
        upload_id = start.json()['data']['id']
        for index, body in enumerate((content[:chunk_size], content[chunk_size:])):
            response = admin_client.put(
                f'/api/v1/files/uploads/{upload_id}/chunks/{index}/', body,
                content_type='application/octet-stream', HTTP_X_CHUNK_SHA256=hashlib.sha256(body).hexdigest())
            assert response.status_code == 200, response.content
        complete = admin_client.post(f'/api/v1/files/uploads/{upload_id}/complete/', {}, format='json')
        assert complete.status_code == 200, complete.content
        assert complete.json()['data']['original_name'] == 'resume.txt'

    def test_resumable_upload_rejects_bad_chunk_digest(self, admin_client):
        body = b'A' * (256 * 1024)
        start = admin_client.post('/api/v1/files/uploads/', {
            'name': 'bad.txt', 'total_size': len(body), 'chunk_size': len(body),
        }, format='json')
        upload_id = start.json()['data']['id']
        response = admin_client.put(
            f'/api/v1/files/uploads/{upload_id}/chunks/0/', body,
            content_type='application/octet-stream', HTTP_X_CHUNK_SHA256='0' * 64)
        assert response.status_code == 422

    def test_resumable_upload_retries_same_chunk_but_rejects_replacement(self, admin_client):
        body = b'A' * (256 * 1024)
        replacement = b'B' * (256 * 1024)
        start = admin_client.post('/api/v1/files/uploads/', {
            'name': 'retry.txt', 'total_size': len(body), 'chunk_size': len(body),
        }, format='json')
        upload_id = start.json()['data']['id']
        url = f'/api/v1/files/uploads/{upload_id}/chunks/0/'
        digest = hashlib.sha256(body).hexdigest()
        first = admin_client.put(url, body, content_type='application/octet-stream', HTTP_X_CHUNK_SHA256=digest)
        assert first.status_code == 200
        repeated = admin_client.put(url, body, content_type='application/octet-stream', HTTP_X_CHUNK_SHA256=digest)
        assert repeated.status_code == 200
        replacement_response = admin_client.put(
            url, replacement, content_type='application/octet-stream',
            HTTP_X_CHUNK_SHA256=hashlib.sha256(replacement).hexdigest())
        assert replacement_response.status_code == 409
        assert ResumableUpload.objects.get(pk=upload_id).chunks['0']['sha256'] == digest

    def test_resumable_upload_expiry_cleanup(self, admin_client):
        body = b'A' * (256 * 1024)
        start = admin_client.post('/api/v1/files/uploads/', {
            'name': 'expired.txt', 'total_size': len(body), 'chunk_size': len(body),
        }, format='json')
        upload_id = start.json()['data']['id']
        row = ResumableUpload.objects.get(pk=upload_id)
        row.expires_at = timezone.now() - timedelta(minutes=1)
        row.save(update_fields=['expires_at'])
        from apps.files.resumable import cleanup_expired_sessions
        assert cleanup_expired_sessions() == 1
        assert ResumableUpload.objects.get(pk=upload_id).status == 'expired'

    @override_settings(FILE_UPLOAD_MAX_SIZE=10)
    def test_upload_exceeds_size_limit(self, admin_client):
        res = admin_client.post('/api/v1/files/', {'file': make_file('big.txt', b'x' * 100)}, format='multipart')
        assert res.status_code == 400


class TestVisibility:
    def test_member_cannot_see_admin_files(self, admin_client, member_client):
        admin_client.post('/api/v1/files/', {'file': make_file('admin-only.txt')}, format='multipart')
        res = member_client.get('/api/v1/files/')
        assert res.status_code == 200
        assert res.json()['data']['items'] == []

    def test_admin_sees_all_files(self, admin_client, member_client, member_user):
        grant_files(member_user, 'file:upload')
        member_client.post('/api/v1/files/', {'file': make_file('member.txt')}, format='multipart')
        res = admin_client.get('/api/v1/files/')
        assert len(res.json()['data']['items']) == 1


class TestDownloadAndDelete:
    def test_download_returns_content_and_counts(self, admin_client):
        upload = admin_client.post('/api/v1/files/', {'file': make_file('dl.txt', b'DATA')}, format='multipart').json()
        res = admin_client.get(f"/api/v1/files/{upload['id']}/download/")
        assert res.status_code == 200
        assert res['Cache-Control'] == 'private, no-store'
        assert res['X-Content-Type-Options'] == 'nosniff'
        assert b''.join(res.streaming_content) == b'DATA'
        assert FileModel.objects.get(id=upload['id']).download_count == 1

    def test_soft_delete_hides_file(self, admin_client):
        upload = admin_client.post('/api/v1/files/', {'file': make_file('del.txt')}, format='multipart').json()
        assert admin_client.delete(f"/api/v1/files/{upload['id']}/").status_code == 204
        record = FileModel.objects.get(id=upload['id'])
        assert record.is_deleted is True
        assert admin_client.get('/api/v1/files/').json()['data']['items'] == []

    def test_purge_admin_only(self, admin_client, member_client):
        upload = admin_client.post('/api/v1/files/', {'file': make_file('purge.txt')}, format='multipart').json()
        # 普通用户（即使非上传者视角）调用物理删除应被拒
        res = member_client.delete(f"/api/v1/files/{upload['id']}/purge/")
        assert res.status_code == 403
        # 管理员物理删除后记录消失，存储中文件移除
        res = admin_client.delete(f"/api/v1/files/{upload['id']}/purge/")
        assert res.status_code == 202
        assert not FileModel.objects.filter(id=upload['id']).exists()
