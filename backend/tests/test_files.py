"""
文件管理测试
"""

import io

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings

from tests.file_permissions import grant_files
from apps.files.models import FileModel


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
        assert res.status_code == 200
        assert not FileModel.objects.filter(id=upload['id']).exists()
