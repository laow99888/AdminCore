"""强制改密的服务端边界、凭据撤销及兼容性。测试使用隔离数据库。"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient
from apps.logs.models import OperationLog

pytestmark = pytest.mark.django_db
User = get_user_model()
INITIAL = 'Initial#Secure8924'
PERSONAL = 'Personal#Secure3782'


def login(user, password=INITIAL):
    client = APIClient()
    response = client.post('/api/v1/auth/login/', {'username': user.username, 'password': password}, format='json')
    assert response.status_code == 200
    body = response.json()
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + body['access'])
    return client, body


@pytest.fixture
def pending_user():
    return User.objects.create_user('pending', 'pending@example.com', INITIAL, must_change_password=True)


@pytest.mark.parametrize('is_admin', [False, True])
def test_pending_login_me_refresh_and_logout_remain_available(pending_user, is_admin):
    pending_user.is_staff = pending_user.is_superuser = is_admin
    pending_user.save()
    client, body = login(pending_user)
    assert body['user']['must_change_password'] is True
    me = client.get('/api/v1/auth/me/').json()['data']
    assert me['must_change_password'] is True and me['permissions'] == []
    refreshed = APIClient().post('/api/v1/auth/refresh/', {'refresh': body['refresh']}, format='json')
    assert refreshed.status_code == 200
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + refreshed.json()['data']['access'])
    assert client.get('/api/v1/users/').status_code == 403
    assert client.post('/api/v1/auth/logout/').status_code == 200
    assert client.get('/api/v1/auth/me/').status_code == 401


@pytest.mark.parametrize('method,path', [
    ('get', 'users/'), ('post', 'users/'), ('get', 'dashboard/stats/'),
    ('get', 'files/'), ('get', 'notifications/'), ('get', 'modules/'),
    ('get', 'schema/'), ('get', 'organization/departments/'),
    ('post', 'auth/register/'),
])
def test_pending_superuser_cannot_bypass_business_gate(pending_user, method, path):
    pending_user.is_staff = pending_user.is_superuser = True
    pending_user.save()
    client, _ = login(pending_user)
    response = getattr(client, method)('/api/v1/' + path)
    assert response.status_code == 403
    assert response.data['data']['reason'] == 'password_change_required'


@pytest.mark.parametrize('old,new,confirm', [
    ('incorrect', PERSONAL, PERSONAL), (INITIAL, INITIAL, INITIAL),
    (INITIAL, 'password', 'password'), (INITIAL, 'pending2026', 'pending2026'),
    (INITIAL, PERSONAL, 'different'),
])
def test_invalid_change_preserves_password_and_restriction(pending_user, old, new, confirm):
    client, _ = login(pending_user)
    response = client.post('/api/v1/auth/change_password/', {
        'old_password': old, 'new_password': new, 'new_password2': confirm}, format='json')
    assert response.status_code == 400
    pending_user.refresh_from_db()
    assert pending_user.must_change_password and pending_user.check_password(INITIAL)
    assert pending_user.session_version == 0
    assert client.get('/api/v1/users/').status_code == 403


def test_success_unlocks_and_revokes_all_old_tokens(pending_user):
    client, body = login(pending_user)
    other_client, other_body = login(pending_user)
    response = client.post('/api/v1/auth/change_password/', {
        'old_password': INITIAL, 'new_password': PERSONAL, 'new_password2': PERSONAL}, format='json')
    assert response.status_code == 200
    pending_user.refresh_from_db()
    assert not pending_user.must_change_password and pending_user.session_version == 1
    for old_client, old_body in [(client, body), (other_client, other_body)]:
        assert old_client.get('/api/v1/auth/me/').status_code == 401
        assert APIClient().post('/api/v1/auth/refresh/', {'refresh': old_body['refresh']}, format='json').status_code == 400
    new_client, _ = login(pending_user, PERSONAL)
    assert new_client.get('/api/v1/notifications/').status_code == 200
    descriptions = list(OperationLog.objects.filter(user=pending_user).values_list('description', flat=True))
    assert '用户完成密码修改' in descriptions
    assert not any(INITIAL in item or PERSONAL in item for item in descriptions)


@pytest.mark.parametrize('required', [None, True, False])
def test_creation_default_and_explicit_choice(admin_client, required):
    payload = {'username': 'created', 'password': INITIAL, 'email': 'created@example.com'}
    if required is not None:
        payload['must_change_password'] = required
    assert admin_client.post('/api/v1/users/', payload, format='json').status_code == 201
    assert User.objects.get(username='created').must_change_password is (required is not False)


@pytest.mark.parametrize('required', [None, True, False])
def test_reset_revokes_even_same_password_and_can_require_change(admin_client, member_user, required):
    client, body = login(member_user, 'Member#12345')
    payload = {'password': 'Member#12345'}
    if required is not None:
        payload['must_change_password'] = required
    assert admin_client.post(f'/api/v1/users/{member_user.pk}/reset_password/', payload, format='json').status_code == 200
    member_user.refresh_from_db()
    assert member_user.must_change_password is (required is not False)
    assert member_user.session_version == 1
    assert client.get('/api/v1/auth/me/').status_code == 401
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': body['refresh']}, format='json').status_code == 400
    new_client, _ = login(member_user, 'Member#12345')
    assert new_client.get('/api/v1/notifications/').status_code == (200 if required is False else 403)


def test_profile_patch_cannot_clear_flag_or_permissions(admin_client, pending_user):
    assert admin_client.patch(f'/api/v1/users/{pending_user.pk}/', {'version': 1, 'must_change_password': False}, format='json').status_code == 200
    pending_user.refresh_from_db()
    assert pending_user.must_change_password


def test_django_session_admin_cannot_bypass_gate(pending_user):
    pending_user.is_staff = pending_user.is_superuser = True
    pending_user.save()
    client = Client()
    client.force_login(pending_user)
    assert client.get('/admin/').status_code == 403
    assert client.post('/admin/logout/').status_code == 200
    assert '_auth_user_id' not in client.session


def test_existing_accounts_default_to_unrestricted(member_client, member_user):
    assert not member_user.must_change_password
    assert member_client.get('/api/v1/notifications/').status_code == 200


def test_django_admin_reset_also_requires_change_and_revokes(member_user, admin_user):
    client = Client()
    client.force_login(admin_user)
    response = client.post(f'/admin/auth_app/user/{member_user.pk}/password/', {
        'password1': INITIAL, 'password2': INITIAL, 'usable_password': 'true'}, follow=False)
    assert response.status_code == 302
    member_user.refresh_from_db()
    assert member_user.must_change_password and member_user.session_version == 1


def test_bootstrap_only_new_standard_admin_requires_change(monkeypatch):
    from django.core.management import call_command
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', INITIAL)
    call_command('bootstrap_admincore')
    user = User.objects.get(username='admin')
    assert user.must_change_password
    user.must_change_password = False
    user.save()
    call_command('bootstrap_admincore')
    user.refresh_from_db()
    assert not user.must_change_password
