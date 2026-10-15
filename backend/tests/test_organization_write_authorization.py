"""组织授权和岗位写入在业务锁前复核操作者及原设备会话。"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.write_authorization import authorize_write
from apps.core.models import DataScopeGrant, Department, OrganizationMembership, Post, UserPost
from apps.core.organization_views import MembershipViewSet
from apps.logs.models import OperationLog
from apps.permissions.models import Role

pytestmark = pytest.mark.django_db
User = get_user_model()
CASES = tuple(
    (resource, operation)
    for resource, operations in (
        ('departments', ('create', 'update', 'delete')),
        ('memberships', ('create', 'update', 'delete')),
        ('scopes', ('create', 'update')),
        ('posts', ('create', 'update', 'delete')),
        ('user-posts', ('create', 'delete')),
    )
    for operation in operations
)
MODELS = (Department, OrganizationMembership, DataScopeGrant, Post, UserPost)


def submission(client, member, resource, operation):
    department = Department.objects.create(name='before')
    alternative = Department.objects.create(name='alternative')
    role = Role.objects.create(name='fixture')
    post = Post.objects.create(code='fixture', name='before')
    if resource == 'departments':
        row, body = department, {'name': 'forbidden'}
    elif resource == 'memberships':
        row = (OrganizationMembership.objects.create(user=member, department=department)
               if operation != 'create' else None)
        body = {'user': str(member.pk), 'department': str(alternative.pk)}
    elif resource == 'scopes':
        row = (DataScopeGrant.objects.create(role=role, resource='user', scope='self')
               if operation != 'create' else None)
        body = {'role': str(role.pk), 'resource': 'user', 'scope': 'all'}
    elif resource == 'posts':
        row, body = post, {'name': 'forbidden'}
        if operation == 'create':
            body['code'] = 'new_fixture'
    else:
        row = UserPost.objects.create(user=member, post=post) if operation != 'create' else None
        body = {'user': str(member.pk), 'post': str(post.pk)}
    path = '/api/v1/organization/' + resource + '/'
    before = [list(model.objects.order_by('pk').values()) for model in MODELS]

    def execute():
        if operation == 'create':
            return client.post(path, {**body, 'version': 0}, format='json')
        if operation == 'update':
            return client.patch(path + str(row.pk) + '/', {**body, 'version': 1}, format='json')
        return client.delete(path + str(row.pk) + '/?version=1')

    def unchanged():
        assert [list(model.objects.order_by('pk').values()) for model in MODELS] == before
        assert not OperationLog.objects.filter(resource__in=(
            'department', 'membership', 'data_scope', 'post', 'user_post')).exists()

    return execute, unchanged


@pytest.mark.parametrize('resource,operation', CASES)
@pytest.mark.parametrize('change,expected', [
    ({'is_staff': False, 'is_superuser': False}, 403),
    ({'is_active': False}, 401),
    ({'must_change_password': True}, 403),
])
def test_stale_entry_actor_cannot_write_after_revocation(admin_user, member_user,
                                                        resource, operation, change, expected):
    client = APIClient()
    client.force_authenticate(admin_user)
    execute, unchanged = submission(client, member_user, resource, operation)
    # Authentication and initial permissions see the intentionally stale object.
    User.objects.filter(pk=admin_user.pk).update(**change)
    response = execute()
    assert response.status_code == expected, response.data
    unchanged()


@pytest.mark.parametrize('resource,operation', CASES)
def test_specific_jwt_device_revoked_after_entry_cannot_write(admin_client, member_user,
                                                            resource, operation):
    from apps.auth_app.models import AuthSession
    from apps.auth_app.sessions import locked_request_session, session_id

    execute, unchanged = submission(admin_client, member_user, resource, operation)

    def revoke_at_lock(request, actor):
        # Revoke the actual authenticated device only after request authentication.
        AuthSession.objects.filter(pk=session_id(request.auth), user=actor).update(revoked_at=timezone.now())
        return locked_request_session(request, actor)

    with patch('apps.auth_app.sessions.locked_request_session', side_effect=revoke_at_lock) as locked:
        response = execute()
    assert response.status_code == 401, response.data
    locked.assert_called_once()
    unchanged()


@pytest.mark.parametrize('resource,operation', CASES)
def test_authorized_writes_still_succeed(admin_client, member_user, resource, operation):
    execute, _ = submission(admin_client, member_user, resource, operation)
    response = execute()
    assert response.status_code == (201 if operation == 'create' else 200), response.data
    assert OperationLog.objects.count() == 1


@pytest.mark.parametrize('resource', ('departments', 'memberships', 'scopes', 'posts', 'user-posts'))
def test_failed_audit_rolls_back_authorized_write(admin_client, member_user, resource):
    execute, unchanged = submission(admin_client, member_user, resource, 'create')
    with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('fixture audit failure')):
        assert execute().status_code == 500
    unchanged()


@pytest.mark.parametrize('resource,operation', [case for case in CASES if case[0] in ('memberships', 'user-posts')])
def test_related_person_is_locked_in_authorization_before_business_write(admin_client, member_user,
                                                                        resource, operation):
    execute, _ = submission(admin_client, member_user, resource, operation)
    module = 'post_views' if resource == 'user-posts' else 'organization_views'

    def observe(request, code=None, **kwargs):
        assert connection.in_atomic_block
        assert member_user.pk in kwargs['related_users']
        assert kwargs['admin'] is True
        assert code == ('post:update' if resource == 'user-posts' else None)
        return authorize_write(request, code, **kwargs)

    with patch('apps.core.' + module + '.authorize_write', side_effect=observe) as locked:
        response = execute()
    assert response.status_code == (201 if operation == 'create' else 200), response.data
    locked.assert_called_once()


def test_membership_delete_audits_locked_current_row_not_old_instance(admin_user, member_user):
    old = Department.objects.create(name='old')
    new = Department.objects.create(name='new')
    stale = OrganizationMembership.objects.create(user=member_user, department=old)
    OrganizationMembership.objects.filter(pk=stale.pk).update(department=new, version=2)
    view = MembershipViewSet()
    view.request = SimpleNamespace(user=admin_user, auth=None, META={'REMOTE_ADDR': '127.0.0.1'})
    view.perform_destroy(stale)
    assert not OrganizationMembership.objects.filter(pk=stale.pk).exists()
    log = OperationLog.objects.get(resource='membership', resource_id=str(stale.pk))
    before = json.loads(log.description)['before']
    assert before['department'] == str(new.pk) and before['version'] == 2
