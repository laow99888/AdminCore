"""文件级 ACL：显式授权、撤销、角色继承和回收站边界。"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.auth_app.models import User
from apps.files.models import FileAccessGrant, FileModel
from tests.file_permissions import grant_files


def file_for(user, name='acl.txt'):
    return FileModel.objects.create(
        original_name=name, uploader=user, file_type='txt', size=5,
        file=SimpleUploadedFile(name, b'hello'),
    )


@pytest.mark.django_db
def test_user_acl_controls_detail_download_and_revocation(admin_client, admin_user, member_user, member_client):
    row = file_for(admin_user)
    grant_files(member_user, 'file:download')
    assert member_client.get(f'/api/v1/files/{row.pk}/').status_code == 404

    response = admin_client.put(f'/api/v1/files/{row.pk}/acl/', {
        'grants': [{'user_id': str(member_user.pk), 'access_level': 'read'}],
    }, format='json')
    assert response.status_code == 200, response.content
    assert member_client.get(f'/api/v1/files/{row.pk}/').status_code == 200
    download = member_client.get(f'/api/v1/files/{row.pk}/download/')
    assert download.status_code == 200
    assert b''.join(download.streaming_content) == b'hello'

    assert admin_client.put(f'/api/v1/files/{row.pk}/acl/', {'grants': []}, format='json').status_code == 200
    assert member_client.get(f'/api/v1/files/{row.pk}/').status_code == 404
    assert member_client.get(f'/api/v1/files/{row.pk}/download/').status_code == 404


@pytest.mark.django_db
def test_role_acl_is_inherited_and_manage_grant_controls_acl(admin_client, admin_user, member_user, member_client):
    row = file_for(admin_user, 'role-acl.txt')
    role = grant_files(member_user, 'file:download')
    response = admin_client.put(f'/api/v1/files/{row.pk}/acl/', {
        'grants': [{'role_id': str(role.pk), 'access_level': 'manage', 'inherit_to_derivatives': True}],
    }, format='json')
    assert response.status_code == 200, response.content
    assert member_client.get(f'/api/v1/files/{row.pk}/').status_code == 200
    assert member_client.get(f'/api/v1/files/{row.pk}/acl/').status_code == 200
    assert FileAccessGrant.objects.filter(file=row, role=role, access_level='manage').exists()


@pytest.mark.django_db
def test_acl_owner_only_and_deleted_file_uses_manage_scope(admin_client, admin_user, member_user, member_client):
    row = file_for(admin_user, 'deleted-acl.txt')
    grant_files(member_user, 'file:download', 'file:recycle')
    row.soft_delete(actor=admin_user)
    assert member_client.get(f'/api/v1/files/{row.pk}/acl/').status_code == 404
    assert admin_client.put(f'/api/v1/files/{row.pk}/acl/', {
        'grants': [{'user_id': str(member_user.pk), 'access_level': 'manage'}],
    }, format='json').status_code == 200
    assert member_client.get(f'/api/v1/files/{row.pk}/acl/').status_code == 200
    # 读取授权不会把已删除文件带回普通列表；回收站仍以 ACL 作为直接 ID 边界。
    assert member_client.get('/api/v1/files/').json()['data']['items'] == []


@pytest.mark.django_db
def test_acl_rejects_unknown_or_duplicate_principal(admin_client, admin_user, member_user):
    row = file_for(admin_user, 'bad-acl.txt')
    duplicate = {'grants': [
        {'user_id': str(member_user.pk), 'access_level': 'read'},
        {'user_id': str(member_user.pk), 'access_level': 'manage'},
    ]}
    assert admin_client.put(f'/api/v1/files/{row.pk}/acl/', duplicate, format='json').status_code == 400
    unknown = {'grants': [{'user_id': '00000000-0000-0000-0000-000000000001', 'access_level': 'read'}]}
    assert admin_client.put(f'/api/v1/files/{row.pk}/acl/', unknown, format='json').status_code == 400


@pytest.mark.django_db
def test_acl_can_disable_derived_access_without_revoking_direct_read(admin_client, admin_user, member_user, member_client):
    row = file_for(admin_user, 'no-derived.txt')
    grant_files(member_user, 'file:download', 'file:process')
    assert admin_client.put(f'/api/v1/files/{row.pk}/acl/', {
        'grants': [{'user_id': str(member_user.pk), 'access_level': 'read', 'inherit_to_derivatives': False}],
    }, format='json').status_code == 200
    assert member_client.get(f'/api/v1/files/{row.pk}/').status_code == 200
    from apps.files.access import file_queryset_for_actor
    assert file_queryset_for_actor(FileModel.objects.filter(pk=row.pk), member_user).exists()
    assert not file_queryset_for_actor(FileModel.objects.filter(pk=row.pk), member_user, derivative=True).exists()


@pytest.mark.django_db
def test_overlapping_acl_grants_return_one_lockable_file(admin_user, member_user):
    from django.db import transaction
    from apps.files.access import file_queryset_for_actor

    row = file_for(admin_user, 'overlapping-grants.txt')
    role = grant_files(member_user, 'file:download')
    FileAccessGrant.objects.create(file=row, user=member_user, access_level='read')
    role_grant = FileAccessGrant.objects.create(file=row, role=role, access_level='manage')
    queryset = file_queryset_for_actor(FileModel.objects.all(), member_user)
    assert list(queryset.values_list('pk', flat=True)) == [row.pk]
    # SQLite 不执行行锁；真实 PostgreSQL 图片验收也会执行同一授权查询。
    assert not queryset.query.distinct
    with transaction.atomic():
        assert queryset.select_for_update().get(pk=row.pk).pk == row.pk
    FileAccessGrant.objects.filter(file=row, user=member_user).delete()
    assert queryset.filter(pk=row.pk).exists()
    role_grant.is_active = False
    role_grant.save(update_fields=['is_active'])
    assert not queryset.filter(pk=row.pk).exists()

