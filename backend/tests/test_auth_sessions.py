"""会话边界、轮换与按设备/用户撤销的 API 回归。"""
from datetime import timedelta
from types import SimpleNamespace
import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import active_sessions, issue_session
from .conftest import ADMIN_PASSWORD, MEMBER_PASSWORD

pytestmark = pytest.mark.django_db


def test_login_refresh_me_do_not_cache_credentials(member_user):
    client = APIClient()
    response = client.post('/api/v1/auth/login/', {'username': 'member', 'password': MEMBER_PASSWORD}, format='json')
    assert response['Cache-Control'] == 'private, no-store'
    tokens = response.json()
    response = client.post('/api/v1/auth/refresh/', {'refresh': tokens['refresh']}, format='json')
    assert response['Cache-Control'] == 'private, no-store'
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.json()['data']['access'])
    assert client.get('/api/v1/auth/me/')['Cache-Control'] == 'private, no-store'


def device(user, agent='Test device'):
    token = issue_session(user, SimpleNamespace(META={
        'REMOTE_ADDR': '127.0.0.1', 'HTTP_USER_AGENT': agent}))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
    return client, token


def test_session_created_without_persisting_raw_refresh(member_user):
    client, token = device(member_user, 'Device\x00' + 'A' * 300)
    session = AuthSession.objects.get(pk=token['sid'])
    assert session.user == member_user and session.refresh_jti == token['jti']
    assert len(session.user_agent) == 256 and '\x00' not in session.user_agent
    assert OutstandingToken.objects.get(jti=token['jti']).token == ''
    assert client.get('/api/v1/auth/me/').status_code == 200


def test_unregistered_legacy_token_requires_new_login(member_user):
    token = RefreshToken.for_user(member_user)
    token['session_version'] = member_user.session_version
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
    assert client.get('/api/v1/auth/me/').status_code == 401
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': str(token)}, format='json').status_code == 400


@pytest.mark.parametrize('change', ['revoked', 'idle', 'absolute', 'password', 'version', 'inactive'])
def test_invalid_session_blocks_access_refresh_and_online(member_user, change):
    client, token = device(member_user)
    session = AuthSession.objects.get(pk=token['sid'])
    if change == 'revoked':
        session.revoked_at = timezone.now()
    elif change == 'idle':
        session.last_seen_at = timezone.now() - timedelta(hours=1)
    elif change == 'absolute':
        session.expires_at = timezone.now() - timedelta(seconds=1)
    elif change == 'password':
        member_user.set_password('Replacement#Password392')
        member_user.save(update_fields=['password'])
    elif change == 'version':
        member_user.session_version += 1
        member_user.save(update_fields=['session_version'])
    else:
        member_user.is_active = False
        member_user.save(update_fields=['is_active'])
    session.save()
    assert client.get('/api/v1/auth/me/').status_code == 401
    response = APIClient().post('/api/v1/auth/refresh/', {'refresh': str(token)}, format='json')
    assert response.status_code == 400
    assert not active_sessions().filter(pk=session.pk).exists()


def test_refresh_is_single_use_and_absolute_lifetime_does_not_extend(member_user):
    _, token = device(member_user)
    session = AuthSession.objects.get(pk=token['sid'])
    session.expires_at = timezone.now() + timedelta(minutes=2)
    session.save(update_fields=['expires_at'])
    client = APIClient()
    first = client.post('/api/v1/auth/refresh/', {'refresh': str(token)}, format='json')
    assert first.status_code == 200
    rotated = RefreshToken(first.json()['data']['refresh'])
    assert rotated['jti'] != token['jti'] and rotated['sid'] == token['sid']
    assert rotated['exp'] <= int(session.expires_at.timestamp())
    from rest_framework_simplejwt.tokens import AccessToken
    assert AccessToken(first.json()['data']['access'])['exp'] <= int(session.expires_at.timestamp())
    assert client.post('/api/v1/auth/refresh/', {'refresh': str(token)}, format='json').status_code == 400
    assert client.post('/api/v1/auth/refresh/', {'refresh': str(rotated)}, format='json').status_code == 200
    assert not OutstandingToken.objects.exclude(token='').exists()


def test_logout_only_current_device(member_user):
    first, token = device(member_user)
    second, _ = device(member_user)
    assert first.post('/api/v1/auth/logout/').status_code == 200
    assert first.get('/api/v1/auth/me/').status_code == 401
    assert second.get('/api/v1/auth/me/').status_code == 200
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': str(token)}, format='json').status_code == 400


def test_personal_list_is_paginated_private_and_whitelisted(member_user, admin_user):
    client, token = device(member_user)
    device(member_user)
    device(admin_user)
    res = client.get('/api/v1/auth/sessions/?page_size=1')
    assert res.status_code == 200 and res['Cache-Control'] == 'private, no-store'
    data = res.json()['data']
    assert data['pagination']['total'] == 2 and len(data['items']) == 1
    item = data['items'][0]
    assert set(item) == {'id', 'created_at', 'last_seen_at', 'expires_at', 'ip_address',
                         'user_agent', 'is_current', 'active'}
    all_items = client.get('/api/v1/auth/sessions/').json()['data']['items']
    assert sum(item['is_current'] for item in all_items) == 1
    assert next(item for item in all_items if item['is_current'])['id'] == token['sid']


def test_revoke_other_device_requires_password_and_preserves_current(member_user):
    first, _ = device(member_user)
    second, token = device(member_user)
    url = f'/api/v1/auth/sessions/{token["sid"]}/'
    assert first.delete(url, {}, format='json').status_code == 400
    assert first.delete(url, {'current_password': 'wrong'}, format='json').status_code == 403
    assert second.get('/api/v1/auth/me/').status_code == 200
    res = first.delete(url, {'current_password': MEMBER_PASSWORD}, format='json')
    assert res.status_code == 200 and res.json()['data']['revoked_count'] == 1
    assert first.get('/api/v1/auth/me/').status_code == 200
    assert second.get('/api/v1/auth/me/').status_code == 401


def test_personal_revoke_cannot_target_another_user(member_user, admin_user):
    client, _ = device(member_user)
    _, target = device(admin_user)
    res = client.delete(f'/api/v1/auth/sessions/{target["sid"]}/',
                        {'current_password': MEMBER_PASSWORD}, format='json')
    assert res.status_code == 404
    assert AuthSession.objects.get(pk=target['sid']).revoked_at is None


def test_personal_revoke_current_session(member_user):
    client, token = device(member_user)
    res = client.delete(f'/api/v1/auth/sessions/{token["sid"]}/',
                        {'current_password': MEMBER_PASSWORD}, format='json')
    assert res.status_code == 200
    assert client.get('/api/v1/auth/me/').status_code == 401


def test_online_directory_only_admin_and_active_sessions(member_user, admin_user):
    member, _ = device(member_user)
    admin, _ = device(admin_user)
    device(member_user)
    assert member.get('/api/v1/auth/online-users/').status_code == 403
    res = admin.get('/api/v1/auth/online-users/?search=member')
    assert res.status_code == 200 and res['Cache-Control'] == 'private, no-store'
    items = res.json()['data']['items']
    assert len(items) == 1 and items[0]['session_count'] == 2
    assert set(items[0]) == {'id', 'username', 'first_name', 'last_name', 'session_count',
                           'last_seen_at', 'is_current_user'}
    assert not items[0]['is_current_user']


def test_admin_revocation_requires_own_password_revokes_target_all_and_audits(member_user, admin_user):
    from apps.logs.models import OperationLog
    admin, _ = device(admin_user)
    first, token = device(member_user)
    second, _ = device(member_user)
    url = f'/api/v1/auth/online-users/{member_user.pk}/revoke/'
    assert admin.post(url, {'current_password': MEMBER_PASSWORD}, format='json').status_code == 403
    res = admin.post(url, {'current_password': ADMIN_PASSWORD}, format='json')
    assert res.status_code == 200 and res.json()['data']['revoked_count'] == 2
    assert first.get('/api/v1/auth/me/').status_code == 401
    assert second.get('/api/v1/auth/me/').status_code == 401
    assert admin.get('/api/v1/auth/me/').status_code == 200
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': str(token)}, format='json').status_code == 400
    log = OperationLog.objects.get(description='revoke_user_sessions')
    assert log.user == admin_user and log.resource_id == str(member_user.pk)
    assert ADMIN_PASSWORD not in log.description


def test_admin_cannot_revoke_self_or_nonexistent_user(admin_user):
    admin, _ = device(admin_user)
    assert admin.post(f'/api/v1/auth/online-users/{admin_user.pk}/revoke/',
                      {'current_password': ADMIN_PASSWORD}, format='json').status_code == 403
    assert admin.post(f'/api/v1/auth/online-users/{uuid.uuid4()}/revoke/',
                      {'current_password': ADMIN_PASSWORD}, format='json').status_code == 404


def test_changing_password_invalidates_every_device(member_user):
    first, _ = device(member_user)
    second, token = device(member_user)
    res = first.post('/api/v1/auth/change_password/', {'old_password': MEMBER_PASSWORD,
        'new_password': 'Changed#Password934', 'new_password2': 'Changed#Password934'}, format='json')
    assert res.status_code == 200
    assert first.get('/api/v1/auth/me/').status_code == 401
    assert second.get('/api/v1/auth/me/').status_code == 401
    assert not active_sessions().exists()
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': str(token)}, format='json').status_code == 400


def test_session_touch_is_rate_limited(member_user):
    client, token = device(member_user)
    before = AuthSession.objects.get(pk=token['sid']).last_seen_at
    client.get('/api/v1/auth/me/')
    assert AuthSession.objects.get(pk=token['sid']).last_seen_at == before
    AuthSession.objects.filter(pk=token['sid']).update(last_seen_at=timezone.now() - timedelta(minutes=2))
    client.get('/api/v1/auth/me/')
    assert AuthSession.objects.get(pk=token['sid']).last_seen_at > before


def test_bootstrap_session_permissions_do_not_expand_existing_roles(admin_user, monkeypatch):
    from io import StringIO
    from django.core.management import call_command
    from apps.permissions.models import Role, RolePermission, Permission, Menu
    admin_user.set_password('Existing-safe-fixture#2026')
    admin_user.save()
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'unused-existing-user')
    role = Role.objects.create(name='系统管理员')
    call_command('bootstrap_admincore', stdout=StringIO())
    assert Permission.objects.filter(code__in=['session:read', 'session:revoke']).count() == 2
    assert not RolePermission.objects.filter(role=role, permission__code__startswith='session:').exists()
    Menu.objects.get(path='/system/online-users').delete()
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not Menu.objects.filter(path='/system/online-users').exists()
