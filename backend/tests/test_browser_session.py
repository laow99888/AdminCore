"""真实 CSRF 检查与数据库会话轮换；不把 APIClient 的 CSRF 豁免当成通过。"""
from datetime import timedelta
from uuid import uuid4

from cryptography.fernet import Fernet
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.auth_app.browser_session import DEV_COOKIE_NAME as COOKIE_NAME, COOKIE_PATH
from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session
from apps.auth_app.totp import hotp
from .conftest import MEMBER_PASSWORD

pytestmark = pytest.mark.django_db
BASE = '/api/v1/auth/'
URL = BASE + 'browser-session/'
ORIGIN = 'http://testserver'


@pytest.fixture(autouse=True)
def transport(settings):
    settings.AUTH_BROWSER_COOKIE_ENABLED = True
    settings.DEBUG = True


def browser():
    return APIClient(enforce_csrf_checks=True, HTTP_ORIGIN=ORIGIN, HTTP_X_ADMINCORE_SESSION='cookie')


def csrf(client):
    response = client.get(URL)
    assert response.status_code == 200
    assert set(response.data['data']) == {'csrf_token'}
    assert response['Cache-Control'] == 'private, no-store'
    return response.data['data']['csrf_token']


def post(client, path, data=None):
    return client.post(path, data or {}, format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)


def login(client):
    csrf(client)
    response = post(client, BASE + 'login/', {'username': 'member', 'password': MEMBER_PASSWORD})
    assert response.status_code == 200, response.data
    assert 'refresh' not in response.data and response.data['session_transport'] == 'cookie'
    return response


def test_disabled_transport_is_closed_and_old_login_is_compatible(settings, member_user):
    settings.AUTH_BROWSER_COOKIE_ENABLED = False
    client = browser()
    assert client.get(URL).status_code == 404
    assert client.post(BASE + 'login/', {'username': 'member', 'password': MEMBER_PASSWORD}, format='json').status_code == 404
    assert not AuthSession.objects.exists()
    legacy = APIClient().post(BASE + 'login/', {'username': 'member', 'password': MEMBER_PASSWORD}, format='json')
    assert set(legacy.data) == {'access', 'refresh', 'user'}
    assert COOKIE_NAME not in legacy.cookies


@pytest.mark.parametrize('origin,proof', [(None, 'valid'), ('null', 'valid'), ('https://evil.example', 'valid'),
                                       (ORIGIN, None), (ORIGIN, 'wrong')])
def test_login_checks_origin_and_csrf_before_creating_session(member_user, settings, origin, proof):
    settings.CSRF_TRUSTED_ORIGINS = ['https://evil.example']
    client = browser()
    token = csrf(client)
    client.defaults.pop('HTTP_ORIGIN')
    headers = {} if origin is None else {'HTTP_ORIGIN': origin}
    if proof is not None:
        headers['HTTP_X_CSRFTOKEN'] = token if proof == 'valid' else proof
    response = client.post(BASE + 'login/', {'username': 'member', 'password': MEMBER_PASSWORD}, format='json', **headers)
    assert response.status_code == 403 and COOKIE_NAME not in response.cookies
    assert not AuthSession.objects.exists()


def test_cookie_scope_and_no_raw_refresh_in_body_or_persistence(member_user):
    client = browser()
    response = login(client)
    cookie = response.cookies[COOKIE_NAME]
    assert cookie['httponly'] and cookie['samesite'] == 'Lax' and cookie['path'] == COOKIE_PATH
    assert not cookie['domain'] and not cookie['secure']  # 只允许调试环境 HTTP
    assert 0 < int(cookie['max-age']) <= 86400
    assert cookie.value not in response.content.decode()
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from apps.logs.models import OperationLog, LoginLog
    assert not OutstandingToken.objects.exclude(token='').exists()
    assert cookie.value not in repr(list(OperationLog.objects.values())) + repr(list(LoginLog.objects.values()))
    assert response.data['csrf_token'] != csrf(APIClient())
    # 持有 Cookie 不能直接调用业务端点；access 仍需以 Bearer 显式提供。
    assert client.get(BASE + 'me/').status_code == 401
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
    assert client.get(BASE + 'me/').status_code == 200


def test_https_sets_secure_and_non_debug_http_is_rejected(settings, member_user):
    settings.SESSION_COOKIE_SECURE = True
    settings.CSRF_COOKIE_SECURE = True
    settings.DEBUG = False
    client = browser()
    assert client.get(URL).status_code == 403
    client.defaults['HTTP_ORIGIN'] = 'https://testserver'
    proof = client.get(URL, secure=True).data['data']['csrf_token']
    response = client.post(BASE + 'login/', {'username': 'member', 'password': MEMBER_PASSWORD},
                           format='json', secure=True, HTTP_X_CSRFTOKEN=proof)
    cookie = response.cookies['__Host-admincore_refresh']
    assert response.status_code == 200 and cookie['secure'] and cookie['httponly']
    assert cookie['path'] == '/' and not cookie['domain'] and COOKIE_NAME not in response.cookies
    settings.SESSION_COOKIE_SECURE = False
    assert client.get(URL, secure=True).status_code == 403


def test_invalid_password_never_sets_refresh_cookie(member_user):
    client = browser()
    csrf(client)
    response = post(client, BASE + 'login/', {'username': 'member', 'password': 'wrong'})
    assert response.status_code == 401 and COOKIE_NAME not in response.cookies
    assert not AuthSession.objects.exists()


def test_browser_endpoint_keeps_anonymous_throttle(monkeypatch):
    from rest_framework.throttling import AnonRateThrottle
    monkeypatch.setattr(AnonRateThrottle, 'THROTTLE_RATES', {'anon': '2/hour'})
    client = browser()
    assert client.get(URL).status_code == 200
    assert client.get(URL).status_code == 200
    response = client.get(URL)
    assert response.status_code == 429 and COOKIE_NAME not in response.cookies


@pytest.mark.parametrize('method', ['post', 'delete'])
def test_cookie_writes_require_csrf_even_with_an_auth_cookie(member_user, method):
    client = browser()
    result = login(client)
    sid = AccessToken(result.data['access'])['sid']
    response = getattr(client, method)(URL, {'session_id': sid}, format='json')
    assert response.status_code == 403 and COOKIE_NAME not in response.cookies
    assert AuthSession.objects.get(pk=sid).revoked_at is None


def test_cookie_rotation_is_one_use_and_does_not_extend_absolute_expiry(member_user):
    client = browser()
    initial = login(client)
    old = client.cookies[COOKIE_NAME].value
    token = AccessToken(initial.data['access'])
    session = AuthSession.objects.get(pk=token['sid'])
    session.expires_at = timezone.now() + timedelta(minutes=2)
    session.save(update_fields=['expires_at'])
    client.credentials(HTTP_AUTHORIZATION='Bearer expired-access-is-ignored')
    response = post(client, URL, {'session_id': token['sid']})
    assert response.status_code == 200
    data = response.data['data']
    assert set(data) == {'access', 'csrf_token', 'session_transport'}
    rotated = client.cookies[COOKIE_NAME].value
    assert rotated != old and AccessToken(data['access'])['sid'] == token['sid']
    assert AccessToken(data['access'])['exp'] <= int(session.expires_at.timestamp())
    assert int(response.cookies[COOKIE_NAME]['max-age']) <= 120
    # 较旧的失败响应不得清除/改写较新的 Cookie。
    client.cookies[COOKIE_NAME] = old
    repeated = post(client, URL)
    assert repeated.status_code == 401 and COOKIE_NAME not in repeated.cookies
    client.cookies[COOKIE_NAME] = rotated
    assert post(client, URL).status_code == 200


@pytest.mark.parametrize('change', ['revoked', 'idle', 'absolute', 'password', 'version', 'inactive'])
def test_cookie_refresh_respects_existing_revocation_rules(member_user, change):
    client = browser()
    login(client)
    session = AuthSession.objects.get()
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
    response = post(client, URL)
    assert response.status_code == 401 and COOKIE_NAME not in response.cookies


@pytest.mark.parametrize('method', ['post', 'delete'])
def test_stale_tab_cannot_rotate_or_logout_replacement_session(member_user, method):
    client = browser()
    login(client)
    before = AuthSession.objects.get()
    response = getattr(client, method)(URL, {'session_id': str(uuid4())}, format='json',
                                        HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
    assert response.status_code == 409 and COOKIE_NAME not in response.cookies
    after = AuthSession.objects.get()
    assert after.refresh_jti == before.refresh_jti and after.revoked_at is None


def test_logout_works_without_access_and_revokes_only_current_device(member_user):
    client = browser()
    response = login(client)
    sid = AccessToken(response.data['access'])['sid']
    other = issue_session(member_user)
    assert client.delete(URL, {'session_id': sid}, format='json').status_code == 403
    assert client.delete(URL, {}, format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value).status_code == 400
    for _ in range(2):
        response = client.delete(URL, {'session_id': sid}, format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        assert response.status_code == 204 and response.cookies[COOKIE_NAME]['max-age'] == 0
    assert AuthSession.objects.get(pk=sid).revoked_at is not None
    assert AuthSession.objects.get(pk=other['sid']).revoked_at is None
    assert post(client, URL).status_code == 401


@pytest.mark.parametrize('payload', [{'refresh': 'must-not-accept-body-token'}, [], {'session_id': 'invalid'}])
def test_cookie_endpoint_rejects_body_credentials_and_invalid_shapes(payload):
    client = browser()
    proof = csrf(client)
    response = client.post(URL, payload, format='json', HTTP_X_CSRFTOKEN=proof)
    assert response.status_code == 400 and COOKIE_NAME not in response.cookies


def test_oversized_cookie_request_is_rejected_before_token_parsing():
    client = browser()
    proof = csrf(client)
    response = client.post(URL, {'padding': 'x' * 4096}, format='json', HTTP_X_CSRFTOKEN=proof)
    assert response.status_code == 400 and COOKIE_NAME not in response.cookies


def test_csrf_rotates_at_login_but_not_during_refresh(member_user):
    client = browser()
    old_proof = csrf(client)
    old_cookie = client.cookies['csrftoken'].value
    response = post(client, BASE + 'login/', {'username': 'member', 'password': MEMBER_PASSWORD})
    assert response.status_code == 200
    new_cookie = client.cookies['csrftoken'].value
    assert new_cookie != old_cookie
    assert client.post(URL, {}, format='json', HTTP_X_CSRFTOKEN=old_proof).status_code == 403
    response = client.post(URL, {}, format='json', HTTP_X_CSRFTOKEN=response.data['csrf_token'])
    assert response.status_code == 200 and client.cookies['csrftoken'].value == new_cookie
    assert client.post(URL, {}, format='json', HTTP_X_CSRFTOKEN=response.data['data']['csrf_token']).status_code == 200


def test_browser_security_errors_follow_requested_language(settings, member_user):
    client = browser()
    client.defaults['HTTP_ACCEPT_LANGUAGE'] = 'en-US'
    login(client)
    response = post(client, URL, {'session_id': str(uuid4())})
    assert response.status_code == 409 and response.data['message'] == 'The browser session has changed. Please reload.'
    response = client.post(URL, {}, format='json')
    assert response.status_code == 403 and response.data['message'] == 'The browser session request failed CSRF validation.'
    client.defaults['HTTP_ORIGIN'] = 'https://evil.example'
    response = post(client, URL)
    assert response.status_code == 403 and response.data['message'] == 'The browser session request origin is invalid.'
    settings.DEBUG = False
    response = client.get(URL)
    assert response.status_code == 403 and response.data['message'] == 'Browser sessions require HTTPS.'


def test_registration_uses_same_cookie_boundary():
    client = browser()
    csrf(client)
    response = post(client, BASE + 'register/', {'username': 'new-cookie-member', 'email': 'new@example.com',
                    'password': MEMBER_PASSWORD, 'password2': MEMBER_PASSWORD})
    assert response.status_code == 201 and COOKIE_NAME in response.cookies
    assert 'refresh' not in response.data['data'] and response.data['data']['session_transport'] == 'cookie'


def test_totp_changes_replace_cookie_and_invalidate_previous_session(settings, member_user, monkeypatch):
    settings.AUTH_TOTP_ENCRYPTION_KEY = Fernet.generate_key().decode()
    client = browser()
    response = login(client)
    old_access = response.data['access']
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + old_access)
    setup = post(client, BASE + 'totp/setup/', {'current_password': MEMBER_PASSWORD})
    secret = setup.data['data']['secret']
    monkeypatch.setattr('apps.auth_app.totp.time.time', lambda: 30000)
    response = post(client, BASE + 'totp/enable/', {'current_password': MEMBER_PASSWORD, 'otp_code': hotp(secret, 1000)})
    assert response.status_code == 200
    assert len(response.data['data']['recovery_codes']) == 10
    assert 'refresh' not in response.data['data'] and COOKIE_NAME in response.cookies
    old = APIClient(HTTP_AUTHORIZATION='Bearer ' + old_access)
    assert old.get(BASE + 'me/').status_code == 401
    assert post(client, URL).status_code == 200
