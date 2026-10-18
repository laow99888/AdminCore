"""个人整理的树约束、并发版本、文件 ACL、租户与迁移兼容边界。"""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections, connection
from rest_framework.test import APIClient

from apps.files.models import FileAccessGrant, FileFolder, FileModel, FileOrganization
from apps.logs.models import OperationLog

pytestmark = pytest.mark.django_db
BASE = '/api/v1/files/'


def file_for(user, **changes):
    return FileModel.objects.create(original_name='合同.txt', file_type='txt', size=5, uploader=user, **changes)


def folder(client, name='合同', parent=None):
    response = client.post(BASE + 'library/folders/', {'name': name, 'parent': parent}, format='json')
    assert response.status_code == 201, response.content
    return response.json()['data']


def organize(client, file, folder=None, tags=None, version=0):
    return client.put(BASE + str(file.pk) + '/organization/', {
        'folder': folder, 'tags': tags or [], 'version': version}, format='json')


def items(client, **params):
    response = client.get(BASE, params)
    assert response.status_code == 200, response.content
    return response.json()['data']['items']


def test_tree_edit_move_and_private_listing(admin_client, member_client):
    root = folder(admin_client)
    child = folder(admin_client, '2026', root['id'])
    response = admin_client.put(BASE + f"library/folders/{child['id']}/", {
        'version': 1, 'name': '归档', 'parent': None}, format='json')
    assert response.status_code == 200, response.content
    assert response.json()['data'] == {**child, 'version': 2, 'name': '归档', 'parent': None}
    data = admin_client.get(BASE + 'library/').json()['data']
    assert len(data['folders']) == 2 and data['tags'] == []
    assert member_client.get(BASE + 'library/').json()['data']['folders'] == []
    assert member_client.put(BASE + f"library/folders/{root['id']}/", {
        'version': 1, 'name': '越权', 'parent': None}, format='json').status_code == 404


def test_tree_cycle_and_subtree_depth_validation(admin_client):
    roots = [folder(admin_client, '0')]
    for index in range(1, 8):
        roots.append(folder(admin_client, str(index), roots[-1]['id']))
    assert admin_client.post(BASE + 'library/folders/', {'name': '9', 'parent': roots[-1]['id']}, format='json').status_code == 400
    url = BASE + f"library/folders/{roots[0]['id']}/"
    assert admin_client.put(url, {'version': 1, 'name': '0', 'parent': roots[-1]['id']}, format='json').status_code == 400
    extra = folder(admin_client, 'extra')
    assert admin_client.put(url, {'version': 1, 'name': '0', 'parent': extra['id']}, format='json').status_code == 400
    assert admin_client.put(url, {'version': 1, 'name': '0', 'parent': roots[0]['id']}, format='json').status_code == 400
    assert FileFolder.objects.get(pk=roots[0]['id']).version == 1


def test_duplicate_names_are_normalized_and_versions_required(admin_client):
    row = folder(admin_client, '合同')
    assert admin_client.post(BASE + 'library/folders/', {'name': ' 合同 ', 'parent': None}, format='json').status_code == 409
    url = BASE + f"library/folders/{row['id']}/"
    assert admin_client.put(url, {'name': '合同', 'parent': None}, format='json').status_code == 400
    assert admin_client.put(url, {'name': '合同', 'parent': None, 'version': 2}, format='json').status_code == 409
    assert admin_client.delete(url, {'version': 2}, format='json').status_code == 409
    folder(admin_client, 'Résumé')
    assert admin_client.post(BASE + 'library/folders/', {'name': 'Re\u0301sume\u0301', 'parent': None}, format='json').status_code == 409
    # 同名可以出现在不同父目录。
    folder(admin_client, '合同', row['id'])


@pytest.mark.parametrize('value', ['', 'a/b', 'a\\b', '\x00', 'x\u200by', 'a' * 81])
def test_folder_invalid_names_and_unknown_fields_rejected(admin_client, value):
    assert admin_client.post(BASE + 'library/folders/', {'name': value, 'parent': None}, format='json').status_code == 400
    assert admin_client.post(BASE + 'library/folders/', {'name': '合法', 'parent': None, 'owner': 'other'}, format='json').status_code == 400


def test_folder_limit_is_per_person(admin_client, admin_user, member_client):
    FileFolder.objects.bulk_create([FileFolder(owner=admin_user, name=str(index)) for index in range(200)])
    assert admin_client.post(BASE + 'library/folders/', {'name': '超额', 'parent': None}, format='json').status_code == 400
    folder(member_client, '未超额')


def test_organization_filter_and_no_mutation_to_file(admin_client, admin_user):
    row, other = file_for(admin_user), file_for(admin_user)
    root = folder(admin_client)
    before = (row.file.name, row.lifecycle_version, row.is_deleted)
    response = organize(admin_client, row, root['id'], ['合同', '2026'])
    assert response.status_code == 200, response.content
    expected = {'version': 1, 'folder': root['id'], 'tags': ['2026', '合同']}
    assert response.json()['data'] == expected
    assert items(admin_client, folder=root['id'], tag='2026')[0]['organization'] == expected
    assert [item['id'] for item in items(admin_client, folder='unfiled')] == [str(other.pk)]
    assert len(items(admin_client, tag='合同')) == 1
    assert len(items(admin_client, search='合同', tag='合同')) == 1
    assert organize(admin_client, row, root['id'], ['stale']).status_code == 409
    assert organize(admin_client, row, tags=['新'], version=1).status_code == 200
    row.refresh_from_db()
    assert (row.file.name, row.lifecycle_version, row.is_deleted) == before
    assert len(items(admin_client, folder='unfiled')) == 2
    assert not FileAccessGrant.objects.filter(file=row).exists()


def test_shared_file_has_independent_private_organization_and_revoke(admin_client, admin_user, member_client, member_user):
    row = file_for(admin_user)
    mine, theirs = folder(admin_client, '秘密目录'), folder(member_client, '我的目录')
    organize(admin_client, row, mine['id'], ['秘密标签'])
    assert organize(member_client, row, theirs['id'], ['成员标签']).status_code == 404
    grant = FileAccessGrant.objects.create(file=row, user=member_user)
    assert items(member_client)[0]['organization'] == {'version': 0, 'folder': None, 'tags': []}
    assert organize(member_client, row, theirs['id'], ['成员标签']).status_code == 200
    assert organize(member_client, row, mine['id'], version=1).status_code == 404
    assert '秘密' not in json.dumps(member_client.get(BASE + 'library/').json(), ensure_ascii=False)
    assert items(admin_client)[0]['organization']['tags'] == ['秘密标签']
    grant.delete()
    assert items(member_client, folder=theirs['id']) == []
    assert member_client.get(BASE + 'library/').json()['data']['tags'] == []
    assert organize(member_client, row, version=1).status_code == 404


def test_deleted_and_special_files_cannot_be_organized(admin_client, admin_user):
    row = file_for(admin_user)
    organize(admin_client, row, tags=['回收标签'])
    row.soft_delete(actor=admin_user)
    assert organize(admin_client, row, version=1).status_code == 404
    assert admin_client.get(BASE + 'library/').json()['data']['tags'] == []
    assert items(admin_client, tag='回收标签') == []
    assert organize(admin_client, file_for(admin_user, purpose='avatar')).status_code == 404


def test_delete_folder_retains_files_tags_and_conflicts_stale_organization(admin_client, admin_user):
    parent = folder(admin_client)
    child = folder(admin_client, '子目录', parent['id'])
    row = file_for(admin_user)
    assert organize(admin_client, row, child['id'], ['保留']).status_code == 200
    parent_url = BASE + f"library/folders/{parent['id']}/"
    assert admin_client.delete(parent_url, {'version': 1}, format='json').status_code == 409
    assert admin_client.delete(BASE + f"library/folders/{child['id']}/", {'version': 1}, format='json').status_code == 200
    organization = items(admin_client)[0]['organization']
    assert organization == {'folder': None, 'tags': ['保留'], 'version': 2}
    assert organize(admin_client, row, tags=['覆盖'], version=1).status_code == 409
    row.refresh_from_db(); assert not row.is_deleted
    assert admin_client.delete(parent_url, {'version': 1}, format='json').status_code == 200


@pytest.mark.parametrize('changes', [{'tags': ['a', 'A']}, {'tags': ['x'] * 11}, {'tags': ['x' * 33]},
    {'tags': ['\x00']}, {'tags': 'x'}, {'version': -1}, {'folder': 'invalid'}, {'owner': 'other'}])
def test_organization_rejects_bad_payload_without_partial_changes(admin_client, admin_user, changes):
    row = file_for(admin_user)
    payload = {'version': 0, 'folder': None, 'tags': [], **changes}
    assert admin_client.put(BASE + str(row.pk) + '/organization/', payload, format='json').status_code == 400
    assert not FileOrganization.objects.filter(file=row).exists()


def test_query_rejects_invalid_duplicate_or_foreign_folder(admin_client, member_client):
    root = folder(admin_client)
    assert member_client.get(BASE, {'folder': root['id']}).status_code == 404
    assert admin_client.get(BASE, {'folder': 'invalid'}).status_code == 400
    assert admin_client.get(BASE + '?folder=unfiled&folder=unfiled').status_code == 400
    assert admin_client.get(BASE, {'tag': 'x' * 33}).status_code == 400


@pytest.mark.parametrize('payload', [[], 'invalid', None])
def test_metadata_requires_object_payload(admin_client, admin_user, payload):
    row = file_for(admin_user)
    assert admin_client.post(BASE + 'library/folders/', payload, format='json').status_code == 400
    assert admin_client.put(BASE + str(row.pk) + '/organization/', payload, format='json').status_code == 400


def test_tag_suggestions_are_bounded_and_only_include_currently_readable_files(admin_client, admin_user):
    from apps.files.models import FileOrganizationTag
    row = file_for(admin_user)
    organization = FileOrganization.objects.create(file=row, owner=admin_user)
    FileOrganizationTag.objects.bulk_create([FileOrganizationTag(organization=organization, name=f'tag-{i:03}') for i in range(105)])
    response = admin_client.get(BASE + 'library/')
    assert response.status_code == 200
    assert response['Cache-Control'] == 'private, no-store'
    assert len(response.json()['data']['tags']) == 100 and response.json()['data']['tags_truncated']
    assert len(items(admin_client, tag='tag-104')) == 1


def test_organization_prefetch_does_not_grow_queries_per_file(admin_user):
    from django.test.utils import CaptureQueriesContext
    from apps.files.library import with_organization
    from apps.files.serializers import FileSerializer
    from apps.files.models import FileOrganizationTag
    for _ in range(25):
        row = file_for(admin_user)
        organization = FileOrganization.objects.create(file=row, owner=admin_user)
        FileOrganizationTag.objects.create(organization=organization, name='采购')
    def count(limit):
        with CaptureQueriesContext(connection) as captured:
            data = FileSerializer(with_organization(FileModel.objects.select_related('uploader'), admin_user)[:limit], many=True).data
            assert len(data) == limit and all(item['organization']['tags'] == ['采购'] for item in data)
        return len(captured)
    assert count(5) == count(25) == 3


def test_metadata_write_rechecks_session_password_and_audit_atomicity(admin_client, admin_user, monkeypatch):
    row = file_for(admin_user)
    from apps.files import library_views
    def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    with monkeypatch.context() as patch:
        patch.setattr(library_views, 'write_audit', fail)
        assert organize(admin_client, row, tags=['审计失败']).status_code == 500
        assert not FileOrganization.objects.filter(file=row).exists()
    assert organize(admin_client, row, tags=['敏感标签']).status_code == 200
    log = OperationLog.objects.filter(resource='file_organization').latest('created_at')
    assert '敏感标签' not in str(log.after_values) and 'content_sha256' in str(log.after_values)
    admin_user.must_change_password = True; admin_user.save(update_fields=['must_change_password'])
    assert organize(admin_client, row, version=1).status_code == 403
    assert admin_client.post(BASE + 'library/folders/', {'name': '拒绝', 'parent': None}, format='json').status_code == 403


def test_personal_organization_is_tenant_scoped_even_for_same_admin(settings, admin_client, admin_user):
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(name='A', slug='file-a')
    second = Tenant.objects.create(name='B', slug='file-b')
    with tenant_context(first.pk):
        row = file_for(admin_user)
    headers = {'HTTP_X_ADMINCORE_TENANT': str(first.pk)}
    root = admin_client.post(BASE + 'library/folders/', {'name': 'A目录', 'parent': None}, format='json', **headers).json()['data']
    assert admin_client.put(BASE + str(row.pk) + '/organization/', {
        'version': 0, 'folder': root['id'], 'tags': ['A标签']}, format='json', **headers).status_code == 200
    other_headers = {'HTTP_X_ADMINCORE_TENANT': str(second.pk)}
    assert admin_client.get(BASE + 'library/', **other_headers).json()['data']['folders'] == []
    assert admin_client.put(BASE + str(row.pk) + '/organization/', {
        'version': 1, 'folder': None, 'tags': []}, format='json', **other_headers).status_code == 404
    assert admin_client.get(BASE, {'folder': root['id']}, **other_headers).status_code == 404
    # 平台未选租户时，目录也不会串读到各租户；跨租户文件只能查看，不能归入全局个人目录。
    assert admin_client.get(BASE + 'library/').json()['data']['folders'] == []
    assert organize(admin_client, row, version=1).status_code == 400


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_duplicate_folder_and_initial_organization_are_serialized():
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实PostgreSQL用户行锁')
    from apps.auth_app.models import User
    user = User.objects.create_user(username='concurrent-file-organizer')
    row = file_for(user)
    def write(kind):
        close_old_connections()
        try:
            client = APIClient(); client.force_authenticate(User.objects.get(pk=user.pk))
            if kind == 'folder':
                return client.post(BASE + 'library/folders/', {'name': '合同', 'parent': None}, format='json').status_code
            return organize(client, row, tags=['并发']).status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ['folder', 'folder'])) == [201, 409]
        assert sorted(pool.map(write, ['organization', 'organization'])) == [200, 409]
    assert FileFolder.objects.filter(owner=user).count() == 1
    assert FileOrganization.objects.filter(owner=user).count() == 1
