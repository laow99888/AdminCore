from io import StringIO
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from apps.approvals.models import ApprovalRequest
from apps.approvals.serializers import ApprovalCreateSerializer
from apps.core.models import Post, UserPost, Department, OrganizationMembership, DataScopeGrant
from apps.logs.models import OperationLog
from apps.permissions.models import Role, UserRole, RolePermission, Permission, Menu

pytestmark = pytest.mark.django_db
User = get_user_model()
POSTS = '/api/v1/organization/posts/'
ASSIGNMENTS = '/api/v1/organization/user-posts/'
PEOPLE = '/api/v1/approvals/assignees/'
DEPARTMENTS = '/api/v1/approvals/assignee-departments/'


def submit(client, user, **extra):
    return client.post('/api/v1/approvals/', {'title': '目录申请', 'content': '申请内容', 'request_type': 'other',
                                            'assignee_id': str(user.pk), **extra}, format='json')


def test_posts_crud_version_code_validation_and_audit(admin_client):
    assert admin_client.post(POSTS, {'code': 'bad-code', 'name': '岗位', 'version': 0}, format='json').status_code == 400
    assert admin_client.post(POSTS, {'code': 'editor', 'name': '岗位', 'version': 1}, format='json').status_code == 400
    response = admin_client.post(POSTS, {'code': 'editor', 'name': '编辑', 'version': 0}, format='json')
    assert response.status_code == 201
    row = response.json()['data']
    url = POSTS + row['id'] + '/'
    assert row['version'] == 1
    assert admin_client.post(POSTS, {'code': 'editor', 'name': '重复', 'version': 0}, format='json').status_code == 400
    assert admin_client.patch(url, {'code': 'changed', 'version': 1}, format='json').status_code == 400
    assert admin_client.patch(url, {'name': '改名'}, format='json').status_code == 409
    assert admin_client.patch(url, {'name': '改名', 'version': 0}, format='json').status_code == 409
    assert admin_client.patch(url, {'name': '改名', 'version': 1}, format='json').json()['data']['version'] == 2
    assert admin_client.delete(url).status_code == 400
    assert admin_client.delete(url + '?version=1').status_code == 409
    assert admin_client.delete(url + '?version=2').status_code == 200
    logs = OperationLog.objects.filter(resource='post', resource_id=row['id']).order_by('created_at')
    assert list(logs.values_list('action', flat=True)) == ['create', 'update', 'delete']
    details = json.loads(logs[1].description)
    assert details['before']['name'] == '编辑' and details['after']['name'] == '改名'


@pytest.mark.parametrize('payload', [[], {'code': 'writer', 'name': '岗位', 'version': 0, 'roles': []},
                                   {'code': 'writer', 'name': '岗位', 'version': 0, 'order': -1}])
def test_reject_unknown_readonly_and_invalid_fields(admin_client, payload):
    assert admin_client.post(POSTS, payload, format='json').status_code == 400
    assert not Post.objects.exists()


def test_multi_post_assignments_preserve_history_and_do_not_grant_roles(admin_client, member_user):
    posts = [Post.objects.create(code=code, name=code) for code in ['editor', 'reviewer']]
    role_count = UserRole.objects.filter(user=member_user).count()
    payload = {'user': str(member_user.pk), 'post': str(posts[0].pk), 'version': 0}
    row = admin_client.post(ASSIGNMENTS, payload, format='json').json()['data']
    assert admin_client.post(ASSIGNMENTS, payload, format='json').status_code == 400
    assert admin_client.post(ASSIGNMENTS, {**payload, 'post': str(posts[1].pk)}, format='json').status_code == 201
    assert UserRole.objects.filter(user=member_user).count() == role_count
    url = POSTS + str(posts[0].pk) + '/'
    assert admin_client.delete(url + '?version=1').status_code == 400
    assert admin_client.patch(url, {'is_active': False, 'version': 1}, format='json').status_code == 200
    assert UserPost.objects.filter(post=posts[0]).exists()
    assert admin_client.get(POSTS + 'choices/').json()['data'][0]['code'] == 'reviewer'
    assert admin_client.post(ASSIGNMENTS, payload, format='json').status_code == 400
    assert admin_client.get(ASSIGNMENTS).json()['data']['pagination']['total'] == 2
    assignment_url = ASSIGNMENTS + row['id'] + '/'
    assert admin_client.patch(assignment_url, {}, format='json').status_code == 405
    assert admin_client.delete(assignment_url + '?version=2').status_code == 409
    assert admin_client.delete(assignment_url + '?version=1').status_code == 200
    assert admin_client.delete(url + '?version=2').status_code == 200
    assert OperationLog.objects.filter(resource='user_post', action='delete', resource_id=row['id']).exists()


def test_inactive_user_cannot_receive_post(admin_client, member_user):
    post = Post.objects.create(code='writer', name='编辑')
    member_user.is_active = False
    member_user.save()
    assert admin_client.post(ASSIGNMENTS, {'user': str(member_user.pk), 'post': str(post.pk), 'version': 0}, format='json').status_code == 400
    assert not UserPost.objects.exists()


def test_post_endpoints_require_admin_even_with_permissions(member_client, member_user):
    role = Role.objects.create(name='岗位权限普通用户')
    UserRole.objects.create(user=member_user, role=role)
    for action in ['read', 'update']:
        perm = Permission.objects.create(resource='post', action=action, code='post:' + action, name=action)
        RolePermission.objects.create(role=role, permission=perm)
    for url in [POSTS, ASSIGNMENTS, '/api/v1/organization/people/', '/api/v1/organization/people/departments/']:
        assert member_client.get(url).status_code == 403
        assert APIClient().get(url).status_code == 401
    assert member_client.post(POSTS, {'code': 'x', 'name': 'x', 'version': 0}, format='json').status_code == 403


def test_directory_minimal_fields_active_search_pagination(member_client, admin_user):
    department = Department.objects.create(name='编辑部门')
    users = [User.objects.create(username=f'writer_{i:02}', first_name='编辑', email='secret@example.com', phone='13812345678') for i in range(12)]
    for user in users:
        OrganizationMembership.objects.create(user=user, department=department)
    User.objects.create(username='writer_disabled', is_active=False)
    response = member_client.get(PEOPLE + '?search=writer&page_size=10')
    assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
    data = response.json()['data']
    assert data['pagination'] == {'total': 12, 'page': 1, 'page_size': 10, 'total_pages': 2}
    assert len(data['items']) == 10
    assert set(data['items'][0]) == {'id', 'username', 'display_name', 'department', 'department_name'}
    assert data['items'][0]['display_name'] == '编辑' and data['items'][0]['department_name'] == '编辑部门'
    assert 'secret@example.com' not in str(data) and '13812345678' not in str(data)
    assert len(member_client.get(PEOPLE + '?search=writer&page=2').json()['data']['items']) == 2
    assert member_client.get(PEOPLE + '?search=编辑').json()['data']['pagination']['total'] == 12
    assert not member_client.get(PEOPLE + '?search=nonexistent').json()['data']['items']
    assert submit(member_client, admin_user).status_code == 201  # 保留原无范围规则。


@pytest.mark.parametrize('query', ['page_size=101', 'page_size=0', 'page=0', 'department=invalid', 'search=' + 'a' * 101])
def test_picker_query_limits(member_client, query):
    assert member_client.get(PEOPLE + '?' + query).status_code == 400


@pytest.mark.parametrize('scope,expected', [('self', {'member'}), ('department', {'member', 'peer'}), ('department_tree', {'member', 'peer', 'child'}), ('custom', {'outsider'}), ('all', {'member', 'peer', 'child', 'outsider'})])
def test_picker_and_submission_share_user_scope(member_client, member_user, scope, expected):
    root = Department.objects.create(name='总部')
    child = Department.objects.create(name='分部', parent=root)
    outside = Department.objects.create(name='外部')
    people = {'member': member_user, **{name: User.objects.create(username=name) for name in ['peer', 'child', 'outsider']}}
    for name, department in [('member', root), ('peer', root), ('child', child), ('outsider', outside)]:
        OrganizationMembership.objects.create(user=people[name], department=department)
    role = Role.objects.create(name='选择范围')
    UserRole.objects.create(user=member_user, role=role)
    grant = DataScopeGrant.objects.create(role=role, resource='user', scope=scope)
    if scope == 'custom': grant.departments.add(outside)
    data = member_client.get(PEOPLE).json()['data']
    assert {row['username'] for row in data['items']} == expected
    department_ids = {str(people[name].organization_membership.department_id) for name in expected}
    departments = member_client.get(DEPARTMENTS).json()['data']
    assert {row['id'] for row in departments['items']} == department_ids
    for name, user in people.items():
        assert submit(member_client, user).status_code == (201 if name in expected else 400)
    role.is_active = False; role.save()
    assert not member_client.get(PEOPLE).json()['data']['items']


def test_hidden_ancestor_and_disabled_department_not_disclosed(member_client, member_user):
    root = Department.objects.create(name='不能泄漏的上级')
    child = Department.objects.create(name='可见部门', parent=root)
    OrganizationMembership.objects.create(user=member_user, department=child)
    role = Role.objects.create(name='本人范围'); UserRole.objects.create(user=member_user, role=role)
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    rows = member_client.get(DEPARTMENTS).json()['data']['items']
    assert rows == [{'id': str(child.pk), 'name': '可见部门', 'parent': None}]
    child.is_active = False; child.save()
    assert member_client.get(PEOPLE).json()['data']['items'][0]['department'] is None
    assert not member_client.get(PEOPLE + '?department=' + str(child.pk)).json()['data']['items']


def test_org_off_preserves_posts_and_picker_still_obeys_scope(admin_client, member_client, member_user):
    post = Post.objects.create(code='editor', name='编辑'); UserPost.objects.create(user=member_user, post=post)
    role = Role.objects.create(name='本人范围'); UserRole.objects.create(user=member_user, role=role)
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    with override_settings(ADMINCORE_MODULES=('approvals', 'notifications')):
        assert admin_client.get(POSTS).status_code == 404
        assert member_client.get(DEPARTMENTS).json()['data'] == {'enabled': False, 'truncated': False, 'items': []}
        assert member_client.get(PEOPLE).json()['data']['items'][0]['department'] is None
        assert member_client.get(PEOPLE + '?department=' + str(post.pk)).status_code == 400
        assert submit(member_client, member_user).status_code == 201
    assert admin_client.get(ASSIGNMENTS).json()['data']['pagination']['total'] == 1
    with override_settings(ADMINCORE_MODULES=()):
        assert member_client.get(PEOPLE).status_code == 404


def test_final_submit_rechecks_account_after_serializer(member_client, admin_user):
    original = ApprovalCreateSerializer.is_valid
    def disable_after_validation(serializer, *args, **kwargs):
        result = original(serializer, *args, **kwargs)
        User.objects.filter(pk=admin_user.pk).update(is_active=False)
        return result
    with patch.object(ApprovalCreateSerializer, 'is_valid', disable_after_validation):
        assert submit(member_client, admin_user).status_code == 400
    assert not ApprovalRequest.objects.exists()


def test_choices_cap_is_explicit_and_directory_query_count_bounded(admin_client, member_client):
    Post.objects.bulk_create([Post(code=f'p{i}', name=f'岗位{i}') for i in range(1001)])
    assert admin_client.get(POSTS + 'choices/').status_code == 400
    department = Department.objects.create(name='部门')
    users = [User.objects.create(username=f'person_{i}') for i in range(30)]
    OrganizationMembership.objects.bulk_create([OrganizationMembership(user=user, department=department) for user in users])
    # JWT / 范围查询固定成本之外，目录仅 COUNT + SELECT，人数增加不产生逐行查询。
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    with CaptureQueriesContext(connection) as small:
        assert member_client.get(PEOPLE + '?search=person&page_size=1').status_code == 200
    with CaptureQueriesContext(connection) as large:
        assert member_client.get(PEOPLE + '?search=person&page_size=30').status_code == 200
    assert len(large) == len(small)


def test_bootstrap_new_post_permissions_do_not_expand_existing_roles(admin_user, monkeypatch):
    admin_user.set_password('Existing-safe-fixture#2026'); admin_user.save()
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'unused-existing-user')
    role = Role.objects.create(name='系统管理员')
    call_command('bootstrap_admincore', stdout=StringIO())
    assert Permission.objects.filter(code__in=['post:read', 'post:update']).count() == 2
    assert not RolePermission.objects.filter(role=role, permission__code__startswith='post:').exists()
    menu = Menu.objects.get(path='/organization/posts'); menu.delete()
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not Menu.objects.filter(path='/organization/posts').exists()
    assert Menu.objects.filter(path='/system/information').exists()


def test_full_display_name_search_and_legacy_username_scope(member_client, member_user, admin_user):
    member_user.first_name = 'John'; member_user.last_name = 'Doe'; member_user.save()
    role = Role.objects.create(name='本人选择'); UserRole.objects.create(user=member_user, role=role)
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    assert member_client.get(PEOPLE + '?search=John%20Doe').json()['data']['items'][0]['username'] == 'member'
    payload = {'title': '兼容用户名', 'content': '内容', 'request_type': 'other', 'assignee_username': 'admin'}
    assert member_client.post('/api/v1/approvals/', payload, format='json').status_code == 400
    payload['assignee_username'] = 'member'
    assert member_client.post('/api/v1/approvals/', payload, format='json').status_code == 201


def test_department_cap_reports_truncation_without_leaking_parent(member_client):
    departments = [Department(name=f'部门{i:04}') for i in range(1001)]
    Department.objects.bulk_create(departments)
    users = [User(username=f'bulk_person_{i}') for i in range(1001)]
    User.objects.bulk_create(users)
    OrganizationMembership.objects.bulk_create([OrganizationMembership(user=user, department=department) for user, department in zip(users, departments)])
    data = member_client.get(DEPARTMENTS).json()['data']
    assert data['truncated'] and data['enabled'] and len(data['items']) == 1000
