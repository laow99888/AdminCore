"""文档修订与容量从公开入口验证，历史文件不覆盖。"""
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.db.models.deletion import ProtectedError
from rest_framework.test import APIClient

from apps.core.models import LifecycleConflict, Tenant, TenantMembership
from apps.core.tenancy import tenant_context
from apps.files.models import FileAccessGrant, FileCapacity, FileDocument, FileModel, FileRevision
from apps.files.capacity import scope_key

pytestmark = pytest.mark.django_db
BASE = '/api/v1/files/'


def upload(client, name='contract.txt', content=b'first'):
    response = client.post(BASE, {'file': SimpleUploadedFile(name, content, content_type='text/plain')})
    assert response.status_code == 201, response.content
    return response.json()['data']


def revisions(client, anchor, version=0, **values):
    return client.post(BASE + anchor + '/versions/', {'version': version, **values}, format='json')


def grant_permissions(user, *codes):
    from apps.permissions.models import Permission, Role, RolePermission, UserRole
    role = Role.objects.create(name='file viewer')
    for code in codes:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={
            'name': code, 'resource': resource, 'action': action})
        RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=user, role=role)


def test_version_append_and_rollback_preserve_bytes_and_references(admin_client):
    a, b = upload(admin_client), upload(admin_client, content=b'second')
    result = revisions(admin_client, a['id'], file_id=b['id'])
    assert result.status_code == 200, result.content
    data = result.json()['data']
    assert data['version'] == 2 and data['current_file'] == b['id']
    assert [item['number'] for item in data['items']] == [2, 1]
    result = revisions(admin_client, a['id'], version=2, restore_number=1)
    assert result.status_code == 200
    assert result.json()['data']['current_file'] == a['id']
    assert result.json()['data']['items'][0]['restored_from'] == 1
    for item in (a, b):
        assert admin_client.get(BASE + item['id'] + '/references/').json()['data']['protected']
        assert admin_client.delete(BASE + item['id'] + '/').status_code == 409
        row = FileModel.objects.get(pk=item['id'])
        with pytest.raises(LifecycleConflict):
            row.hard_delete()
        with pytest.raises(ProtectedError):
            row.delete()
    for item, content in ((a, b'first'), (b, b'second')):
        response = admin_client.get(BASE + item['id'] + '/download/')
        assert b''.join(response.streaming_content) == content


def test_append_rejects_stale_duplicate_membership_unknown_special_and_deleted(admin_client, admin_user):
    a, b, c, d = [upload(admin_client) for _ in range(4)]
    assert revisions(admin_client, a['id'], file_id=b['id']).status_code == 200
    assert revisions(admin_client, a['id'], file_id=c['id']).status_code == 409
    assert revisions(admin_client, a['id'], version=2, file_id=b['id']).status_code == 409
    assert revisions(admin_client, c['id'], file_id=b['id']).status_code == 409
    assert revisions(admin_client, a['id'], version=2, restore_number=999).status_code == 404
    row = FileModel.objects.get(pk=d['id']); row.soft_delete(actor=admin_user)
    assert revisions(admin_client, a['id'], version=2, file_id=d['id']).status_code == 404
    row = FileModel.objects.get(pk=c['id']); row.purpose = 'avatar'; row.save(update_fields=['purpose'])
    assert revisions(admin_client, a['id'], version=2, file_id=c['id']).status_code == 404
    assert FileRevision.objects.count() == 2 and FileDocument.objects.count() == 1


def test_history_filters_each_file_acl_and_rechecks_current_acl(admin_client, admin_user, member_client, member_user):
    grant_permissions(member_user, 'file:read', 'file:upload')
    a, b = upload(admin_client), upload(admin_client)
    revisions(admin_client, a['id'], file_id=b['id'])
    grant = FileAccessGrant.objects.create(file_id=b['id'], user=member_user)
    result = member_client.get(BASE + b['id'] + '/versions/')
    assert result.status_code == 200 and len(result.json()['data']['items']) == 1
    assert a['id'] not in str(result.json())
    assert revisions(member_client, b['id'], version=2, restore_number=1).status_code == 404
    assert revisions(member_client, b['id'], version=2, file_id=a['id']).status_code == 404
    FileAccessGrant.objects.create(file_id=a['id'], user=member_user)
    assert len(member_client.get(BASE + b['id'] + '/versions/').json()['data']['items']) == 2
    grant.delete()
    assert member_client.get(BASE + a['id'] + '/versions/').status_code == 404
    assert member_client.get(BASE + b['id'] + '/versions/').status_code == 404


@pytest.mark.parametrize('payload', [[], {'version': 0}, {'version': 0, 'file_id': 'bad'},
    {'version': 0, 'file_id': str(uuid.uuid4()), 'restore_number': 1}, {'version': 0, 'unknown': 1}])
def test_bad_revision_input(admin_client, payload):
    a = upload(admin_client)
    assert admin_client.post(BASE + a['id'] + '/versions/', payload, format='json').status_code == 400
    assert not FileDocument.objects.exists()


def test_history_query_validation_and_no_history(admin_client):
    a = upload(admin_client)
    response = admin_client.get(BASE + a['id'] + '/versions/')
    assert response['Cache-Control'] == 'private, no-store'
    assert response.json()['data']['version'] == 0 and response.json()['data']['items'] == []
    for query in ('?page=0', '?page=1&page=1', '?owner_id=other', '?page=1001'):
        assert admin_client.get(BASE + a['id'] + '/versions/' + query).status_code == 400


def test_write_revocation_and_audit_rollback(admin_client, admin_user, monkeypatch):
    from apps.files import versions
    a, b = upload(admin_client), upload(admin_client)
    def fail(**kwargs):
        raise RuntimeError('audit unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(versions, 'write_audit', fail)
        assert revisions(admin_client, a['id'], file_id=b['id']).status_code == 500
    assert not FileRevision.objects.exists() and not FileDocument.objects.exists()
    admin_user.must_change_password = True; admin_user.save(update_fields=['must_change_password'])
    assert revisions(admin_client, a['id'], file_id=b['id']).status_code == 403


def test_capacity_limits_ordinary_and_direct_uploads_recycle_counts_until_purge(admin_client, admin_user):
    a = upload(admin_client)
    data = admin_client.get(BASE + 'capacity/').json()['data']
    assert data == {'used_bytes': 5, 'limit_bytes': 0, 'remaining_bytes': None, 'version': 0}
    response = admin_client.put(BASE + 'capacity/', {'owner_id': str(admin_user.pk), 'limit_bytes': 8, 'version': 0}, format='json')
    assert response.status_code == 200
    response = admin_client.post(BASE, {'file': SimpleUploadedFile('no.txt', b'too long')})
    assert response.status_code == 409 and FileModel.objects.count() == 1
    from apps.core.exceptions import APIError
    with pytest.raises(APIError):
        FileModel.objects.create(uploader=admin_user, original_name='direct.txt', size=9, file='fake.txt')
    assert admin_client.delete(BASE + a['id'] + '/').status_code == 204
    assert admin_client.get(BASE + 'capacity/').json()['data']['used_bytes'] == 5
    FileModel.objects.get(pk=a['id']).hard_delete()
    assert admin_client.get(BASE + 'capacity/').json()['data']['used_bytes'] == 0
    upload(admin_client, content=b'12345678')
    assert admin_client.put(BASE + 'capacity/', {'owner_id': str(admin_user.pk), 'limit_bytes': 0, 'version': 0}, format='json').status_code == 409
    assert admin_client.put(BASE + 'capacity/', {'owner_id': str(admin_user.pk), 'limit_bytes': 1, 'version': 1}, format='json').status_code == 200


def test_capacity_ownership_and_admin_target(admin_client, admin_user, member_client, member_user):
    grant_permissions(member_user, 'file:read', 'file:upload')
    assert member_client.get(BASE + 'capacity/').status_code == 200
    assert member_client.get(BASE + 'capacity/', {'owner_id': str(admin_user.pk)}).status_code == 403
    assert member_client.put(BASE + 'capacity/', {'owner_id': str(member_user.pk), 'limit_bytes': 1, 'version': 0}, format='json').status_code == 403
    assert admin_client.get(BASE + 'capacity/', {'owner_id': str(member_user.pk)}).json()['data']['version'] == 0
    assert admin_client.put(BASE + 'capacity/', {'owner_id': str(member_user.pk), 'limit_bytes': 1, 'version': 0}, format='json').status_code == 200
    assert admin_client.get(BASE + 'capacity/', {'owner_id': str(uuid.uuid4())}).status_code == 404
    upload(admin_client)
    assert member_client.post(BASE, {'file': SimpleUploadedFile('large.txt', b'12')}).status_code == 409


def test_tenant_scope_including_unselected_platform_admin(admin_user, settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    one, two = [Tenant.objects.create(name=name, slug=name) for name in ('one', 'two')]
    for tenant in (one, two):
        TenantMembership.objects.create(tenant=tenant, user=admin_user)
    client = APIClient(); client.force_authenticate(admin_user)
    client.credentials(HTTP_X_ADMINCORE_TENANT=str(one.pk))
    a, b = upload(client), upload(client)
    assert revisions(client, a['id'], file_id=b['id']).status_code == 200
    with tenant_context(two.pk):
        other = FileModel.objects.create(uploader=admin_user, size=10, file='tenant.txt', original_name='tenant.txt')
        FileCapacity.objects.filter(scope_key=scope_key(admin_user.pk, two.pk)).update(limit_bytes=10)
    assert revisions(client, a['id'], version=2, file_id=str(other.pk)).status_code == 404
    assert client.get(BASE + 'capacity/').json()['data']['used_bytes'] == 10
    client.credentials()
    assert client.get(BASE + a['id'] + '/versions/').status_code == 404
    assert client.get(BASE + 'capacity/').status_code == 400


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_upload_cannot_exceed_capacity(admin_user):
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实PostgreSQL额度锁')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections
    from apps.core.exceptions import APIError
    FileCapacity.objects.create(owner=admin_user, scope_key=scope_key(admin_user.pk, None), limit_bytes=10)
    barrier = Barrier(2)
    def run():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            with transaction.atomic():
                FileModel.objects.create(uploader_id=admin_user.pk, size=6, file='test.txt', original_name='test.txt')
            return 'ok'
        except APIError:
            return 'quota'
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: run(), range(2))) == ['ok', 'quota']
    assert FileModel.objects.filter(uploader=admin_user).count() == 1
