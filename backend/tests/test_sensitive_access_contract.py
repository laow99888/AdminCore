"""用户敏感字段的逐次授权、白名单响应与批量导出边界。"""
import csv
import io
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.auth_app.sessions import issue_session
from apps.core.models import DataScopeGrant
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.users.models import UserProfile
from .conftest import ADMIN_PASSWORD, MEMBER_PASSWORD

pytestmark = pytest.mark.django_db
User = get_user_model()
EMAIL, PHONE, LEGACY_PHONE = 'person.private@example.test', '13876543210', '13987654321'


@pytest.fixture
def sensitive_member(member_user):
    member_user.email = EMAIL
    member_user.phone = PHONE
    member_user.save(update_fields=['email', 'phone'])
    UserProfile.objects.update_or_create(user=member_user, defaults={'phone': LEGACY_PHONE})
    return member_user


def grant(user, *codes):
    role = Role.objects.create(name='sensitive-' + str(Role.objects.count()))
    UserRole.objects.create(user=user, role=role)
    for code in codes:
        resource, action = code.split(':', 1)
        permission, _ = Permission.objects.get_or_create(code=code,
            defaults={'name': code, 'resource': resource, 'action': action})
        RolePermission.objects.create(role=role, permission=permission)
    return role


def reveal(client, target, password, **extra):
    return client.post(f'/api/v1/users/{target.pk}/sensitive/',
        {'current_password': password, **extra}, format='json')


def test_management_list_detail_and_updates_are_always_masked(admin_client, sensitive_member):
    listing = admin_client.get('/api/v1/users/')
    row = next(item for item in listing.json()['data']['items'] if item['id'] == str(sensitive_member.pk))
    detail = admin_client.get(f'/api/v1/users/{sensitive_member.pk}/').json()['data']
    patched = admin_client.patch(f'/api/v1/users/{sensitive_member.pk}/', {'first_name': 'safe'}, format='json').json()['data']
    for item in (row, detail, patched):
        assert item['email'] != EMAIL and '*' in item['email']
        if 'phone' in item:
            assert item['phone'] != PHONE and '*' in item['phone']
    assert detail['profile']['phone'] != LEGACY_PHONE and '*' in detail['profile']['phone']
    assert all(value not in str(listing.json()) + str(detail) + str(patched) for value in (EMAIL, PHONE, LEGACY_PHONE))


def test_created_user_response_masks_input_email(admin_client):
    response = admin_client.post('/api/v1/users/', {'username': 'new-sensitive',
        'email': EMAIL, 'password': 'Created#Password971'}, format='json')
    assert response.status_code == 201
    assert EMAIL not in str(response.json()) and '*' in response.json()['data']['email']
    assert User.objects.get(username='new-sensitive').email == EMAIL


def test_current_user_me_and_personal_profile_retain_own_raw_values(member_client, sensitive_member):
    for path in ('me', 'profile'):
        response = member_client.get(f'/api/v1/auth/{path}/')
        assert response.status_code == 200
        assert response.json()['data']['email'] == EMAIL
        assert response.json()['data']['phone'] == PHONE


@pytest.mark.parametrize('codes', [(), ('user:read',), ('user:sensitive_read',)])
def test_raw_reveal_needs_both_permissions(member_client, sensitive_member, codes):
    if codes:
        grant(sensitive_member, *codes)
    response = reveal(member_client, sensitive_member, MEMBER_PASSWORD)
    assert response.status_code == 403
    assert EMAIL not in str(response.json()) and PHONE not in str(response.json())


def test_permission_and_password_confirmation_reveal_only_requested_fields(member_client, sensitive_member):
    grant(sensitive_member, 'user:read', 'user:sensitive_read')
    before = OperationLog.objects.count()
    response = reveal(member_client, sensitive_member, MEMBER_PASSWORD)
    assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
    assert response.json()['data'] == {'email': EMAIL, 'phone': PHONE}
    audit = OperationLog.objects.order_by('-created_at').first()
    assert OperationLog.objects.count() == before + 1 and audit.user == sensitive_member
    assert all(value not in str(audit.description) for value in (EMAIL, PHONE, MEMBER_PASSWORD))
    # 每次请求重新确认，不能依赖前一次成功或客户端缓存。
    response = member_client.post(f'/api/v1/users/{sensitive_member.pk}/sensitive/', {}, format='json')
    assert response.status_code == 400


def test_reveal_refuses_wrong_password_without_audit_or_data(admin_client, sensitive_member):
    before = OperationLog.objects.count()
    response = reveal(admin_client, sensitive_member, 'incorrect')
    assert response.status_code == 403
    assert OperationLog.objects.count() == before
    assert EMAIL not in str(response.json()) and PHONE not in str(response.json())


def test_raw_permission_cannot_bypass_user_data_scope(member_client, sensitive_member, admin_user):
    role = grant(sensitive_member, 'user:read', 'user:sensitive_read')
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    response = reveal(member_client, admin_user, MEMBER_PASSWORD)
    assert response.status_code == 404


def test_reveal_cache_failure_is_closed_and_hides_error_details(admin_client, sensitive_member):
    broken_cache = Mock()
    broken_cache.get.side_effect = RuntimeError('private-redis-credentials')
    with patch('apps.auth_app.reauthentication.cache', broken_cache):
        response = reveal(admin_client, sensitive_member, ADMIN_PASSWORD)
    assert response.status_code == 503
    assert all(value not in str(response.json()) for value in (EMAIL, PHONE, 'private-redis-credentials'))


def test_revoked_actor_session_cannot_read_raw_fields(admin_user, sensitive_member):
    token = issue_session(admin_user)
    from apps.auth_app.models import AuthSession
    from django.utils import timezone
    AuthSession.objects.filter(pk=token['sid']).update(revoked_at=timezone.now())
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    response = reveal(client, sensitive_member, ADMIN_PASSWORD)
    assert response.status_code == 401
    assert EMAIL not in str(response.json()) and PHONE not in str(response.json())


def test_sensitive_action_rejects_unknown_fields_and_get(admin_client, sensitive_member):
    assert reveal(admin_client, sensitive_member, ADMIN_PASSWORD, bypass=True).status_code == 400
    response = admin_client.get(f'/api/v1/users/{sensitive_member.pk}/sensitive/')
    assert response.status_code in (403, 405)
    assert response['Cache-Control'] == 'private, no-store'
    assert EMAIL not in str(response.json()) and PHONE not in str(response.json())


@pytest.mark.parametrize('format', ['csv', 'xlsx'])
def test_export_remains_masked_even_with_raw_permission(admin_client, sensitive_member, format):
    response = admin_client.get(f'/api/v1/data-io/export/?resource=users&export_format={format}')
    assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
    if format == 'csv':
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    else:
        rows = list(load_workbook(io.BytesIO(response.content), data_only=True).active.values)
    assert any(row[0] == sensitive_member.username for row in rows[1:])
    assert EMAIL not in str(rows) and PHONE not in str(rows) and LEGACY_PHONE not in str(rows)
    assert '*' in str(rows)


def test_private_email_is_not_an_indirect_search_oracle(admin_client, sensitive_member):
    listing = admin_client.get('/api/v1/users/?search=person.private%40example.test')
    assert listing.status_code == 200 and listing.json()['data']['pagination']['total'] == 0
    response = admin_client.get('/api/v1/data-io/export/?resource=users&search=person.private%40example.test')
    assert response.status_code == 200
    assert len(list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))) == 1
    listing = admin_client.get('/api/v1/users/?search=member')
    assert any(row['id'] == str(sensitive_member.pk) for row in listing.json()['data']['items'])


@pytest.mark.parametrize('field,value', [('phone', '138****3210'), ('email', 'pe***@example.test')])
def test_masked_placeholder_cannot_be_written_back(admin_client, sensitive_member, field, value):
    response = admin_client.patch(f'/api/v1/users/{sensitive_member.pk}/', {field: value}, format='json')
    assert response.status_code == 400
    sensitive_member.refresh_from_db()
    assert sensitive_member.email == EMAIL and sensitive_member.phone == PHONE


def test_valid_new_contact_input_writes_raw_but_returns_mask(admin_client, sensitive_member):
    email, phone = 'replacement@example.test', '+86 13654321098'
    response = admin_client.patch(f'/api/v1/users/{sensitive_member.pk}/',
        {'email': email, 'phone': phone}, format='json')
    assert response.status_code == 200
    assert email not in str(response.json()) and phone not in str(response.json())
    sensitive_member.refresh_from_db()
    assert sensitive_member.email == email and sensitive_member.phone == phone


def test_django_admin_contact_fields_are_not_editable(admin_user, sensitive_member):
    from django.contrib import admin
    profile = UserProfile.objects.get(user=sensitive_member)
    for model, obj in ((User, sensitive_member), (UserProfile, profile)):
        request = type('Request', (), {'user': admin_user})()
        form = admin.site._registry[model].get_form(request, obj)
        assert 'phone' not in form.base_fields
        assert 'email' not in form.base_fields
