"""An isolated real HTTP OIDC peer signs RSA tokens and consumes PKCE codes; no vendor credentials."""
import base64
import hashlib
import json
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

import pytest
import requests
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.utils import timezone
from joserfc import jwt
from joserfc.jwk import RSAKey
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.auth_app.models import AuthSession, TOTPDevice
from apps.auth_app.totp import hotp
from apps.sso import protocol, service
from apps.sso.configuration import SSOUnavailable, provider
from apps.sso.models import ExternalIdentity, LoginFlow, SSOSession
from apps.logs.models import LoginLog, OperationLog

pytestmark = pytest.mark.django_db
BASE = '/api/v1/sso/'
ORIGIN = 'http://localhost:9000'
PASSWORD = 'SSO-fixture-only#2026'


@contextmanager
def oidc_peer():
    key = RSAKey.generate_key(2048, parameters={'kid': 'fixture-key'})
    state = {'codes': {}, 'claims': {}, 'subject': 'employee-001', 'token_requests': [], 'jwks_requests': [], 'mode': ''}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, value, status=200):
            content = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            path, query = urlsplit(self.path).path, parse_qs(urlsplit(self.path).query)
            if path == '/authorize':
                assert query['client_id'] == ['fixture-client'] and query['response_type'] == ['code']
                assert query['scope'] == ['openid'] and query['code_challenge_method'] == ['S256']
                assert query['redirect_uri'] == [ORIGIN + BASE + 'callback/']
                assert query['max_age'] == ['300'] and query['prompt'] == ['login']
                code = secrets.token_urlsafe(24)
                state['codes'][code] = query
                self.send_response(302)
                self.send_header('Location', query['redirect_uri'][0] + '?' + urlencode({'code': code, 'state': query['state'][0], 'iss': state['issuer']}))
                self.end_headers()
            elif path == '/jwks':
                state['jwks_requests'].append(dict(self.headers))
                if state['mode'] == 'jwks_fail':
                    return self.send_json({'error': 'unavailable'}, 503)
                keys = [key.as_dict(private=False)]
                if state['mode'] == 'duplicate_kid': keys.append(key.as_dict(private=False))
                if state['mode'] == 'private_jwk': keys = [key.as_dict(private=True)]
                self.send_json({'keys': keys})
            else:
                self.send_json({'error': 'not_found'}, 404)

        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            params = parse_qs(self.rfile.read(length).decode())
            state['token_requests'].append(params)
            if state['mode'] == 'token_fail':
                return self.send_json({'error': 'unavailable'}, 503)
            if state['mode'] == 'redirect':
                self.send_response(302)
                self.send_header('Location', 'http://127.0.0.1:1/private')
                self.end_headers()
                return
            assert self.path == '/token'
            assert self.headers['Authorization'] == 'Basic ' + base64.b64encode(b'fixture-client:fixture-secret').decode()
            original = state['codes'].pop(params.get('code', [''])[0], None)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(params.get('code_verifier', [''])[0].encode()).digest()).rstrip(b'=').decode()
            if original is None or original['code_challenge'] != [challenge] or params.get('redirect_uri') != original['redirect_uri']:
                return self.send_json({'error': 'invalid_grant'}, 400)
            assert params['grant_type'] == ['authorization_code']
            now = int(time.time())
            claims = {'iss': state['issuer'], 'sub': state['subject'], 'aud': 'fixture-client',
                      'iat': now, 'exp': now + 300, 'auth_time': now, 'nonce': original['nonce'][0],
                      'email': 'same@example.com', 'email_verified': True, **state['claims']}
            header = {'alg': 'RS256', 'kid': 'unknown-key' if state['mode'] == 'unknown_kid' else 'fixture-key'}
            token = jwt.encode(header, claims, key)
            if state['mode'] == 'bad_signature':
                token = jwt.encode(header, claims, RSAKey.generate_key(2048))
            if state['mode'] == 'alg_none':
                token = base64.urlsafe_b64encode(b'{"alg":"none","kid":"fixture-key"}').decode().rstrip('=') + '.' + token.split('.')[1] + '.'
            if state['mode'] == 'oversize':
                token = 'x' * 70000
            result = {'id_token': token, 'access_token': 'idp-fixture-access-secret', 'token_type': 'Bearer'}
            if state['mode'] == 'no_id_token':
                del result['id_token']
            self.send_json(result)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    state['issuer'] = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def peer(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'sso')
    settings.ROOT_URLCONF = 'tests.sso_urls'
    settings.SSO_TEST_ALLOW_LOOPBACK = True
    settings.SSO_FRONTEND_ORIGIN = ORIGIN
    settings.SSO_REDIRECT_URI = ORIGIN + BASE + 'callback/'
    settings.SSO_CLIENT_ID, settings.SSO_CLIENT_SECRET = 'fixture-client', 'fixture-secret'
    settings.SSO_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.SSO_SESSION_SECONDS = 3600
    with oidc_peer() as value:
        settings.SSO_ISSUER = value['issuer']
        settings.SSO_AUTHORIZATION_ENDPOINT = value['issuer'] + '/authorize'
        settings.SSO_TOKEN_ENDPOINT = value['issuer'] + '/token'
        settings.SSO_JWKS_URI = value['issuer'] + '/jwks'
        yield value


@pytest.fixture
def member(peer):
    user = get_user_model().objects.create_user('sso-member', email='same@example.com', password=PASSWORD)
    ExternalIdentity.objects.create(user=user, issuer=peer['issuer'], subject='employee-001')
    return user


def browser():
    return APIClient(HTTP_ORIGIN=ORIGIN)


def begin(client):
    response = client.post(BASE + 'start/', {}, format='json')
    assert response.status_code == 200, response.data
    with requests.Session() as session:
        session.trust_env = False
        authorized = session.get(response.json()['data']['authorization_url'], allow_redirects=False, timeout=5)
    assert authorized.status_code == 302
    return authorized.headers['Location']


def authorized(client):
    response = client.get(begin(client))
    assert response.status_code == 302 and response['Location'].endswith('result=ready'), response.content
    return response


def complete(client, **values):
    return client.post(BASE + 'complete/', values, format='json')


def local_admin():
    admin = get_user_model().objects.create_superuser('sso-admin', 'admin@example.com', PASSWORD)
    client = APIClient()
    login = client.post('/api/v1/auth/login/', {'username': admin.username, 'password': PASSWORD}, format='json')
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + login.json()['access'])
    return admin, client


def test_real_code_pkce_rsa_flow_one_use_local_permissions_and_short_session(member, peer):
    client = browser()
    authorized(client)
    flow = LoginFlow.objects.get()
    assert flow.encrypted_verifier == '' and flow.consumed_at and flow.identity.user_id == member.pk
    assert not AuthSession.objects.filter(user=member).exists()
    assert client.get(BASE + 'status/').json()['data']['mfa_required'] is False
    result = complete(client)
    assert result.status_code == 200, result.data
    token = AccessToken(result.json()['data']['access'])
    assert token['sso'] is True
    link = SSOSession.objects.get()
    assert 3500 < (link.session.expires_at - timezone.now()).total_seconds() <= 3600
    authenticated = APIClient()
    authenticated.credentials(HTTP_AUTHORIZATION='Bearer ' + result.json()['data']['access'])
    assert authenticated.get('/api/v1/auth/me/').status_code == 200
    assert authenticated.get('/api/v1/users/').status_code == 403
    assert complete(client).status_code == 401
    assert 'Authorization' not in peer['jwks_requests'][0]
    assert not get_user_model().objects.get(pk=member.pk).email_verified
    logs = repr(list(OperationLog.objects.values())) + repr(list(LoginLog.objects.values()))
    assert 'idp-fixture-access-secret' not in logs and 'fixture-secret' not in logs and PASSWORD not in logs
    assert 'id_token' not in repr(flow.__dict__)


def test_cookie_completion_requires_csrf_before_consuming_real_oidc_flow(settings, member, peer):
    from apps.auth_app.browser_session import DEV_COOKIE_NAME as COOKIE_NAME
    settings.AUTH_BROWSER_COOKIE_ENABLED = True
    settings.DEBUG = True
    client = APIClient(enforce_csrf_checks=True, HTTP_ORIGIN=ORIGIN, HTTP_HOST='localhost:9000')
    authorized(client)
    client.defaults['HTTP_X_ADMINCORE_SESSION'] = 'cookie'
    response = complete(client)
    assert response.status_code == 403 and COOKIE_NAME not in response.cookies
    assert LoginFlow.objects.get().completed_at is None and not SSOSession.objects.exists()
    csrf = client.get('/api/v1/auth/browser-session/').data['data']['csrf_token']
    response = client.post(BASE + 'complete/', {}, format='json', HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 200
    assert 'refresh' not in response.data['data'] and response.cookies[COOKIE_NAME]['httponly']
    access = AccessToken(response.data['data']['access'])
    assert access['sso'] is True
    rotated = client.post('/api/v1/auth/browser-session/', {'session_id': access['sid']},
                          format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
    assert rotated.status_code == 200 and 'refresh' not in rotated.data['data']
    again = client.post(BASE + 'complete/', {}, format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
    assert again.status_code == 401


@pytest.mark.parametrize('claims', [
    {'nonce': 'wrong-nonce'}, {'iss': 'https://other.example'}, {'aud': 'other-client'},
    {'aud': ['fixture-client', 'other']}, {'azp': 'other-client'}, {'sub': ''},
    {'exp': 1}, {'iat': int(time.time()) + 600}, {'auth_time': 1}, {'auth_time': True},
    {'nbf': int(time.time()) + 600}, {'exp': int(time.time()) + 9000},
])
def test_bad_signed_oidc_claims_are_rejected(member, peer, claims):
    peer['claims'] = claims
    client = browser()
    response = client.get(begin(client))
    assert response['Location'].endswith('result=failed')
    assert not SSOSession.objects.exists()
    assert LoginFlow.objects.get().consumed_at is not None


@pytest.mark.parametrize('mode', ['token_fail', 'jwks_fail', 'redirect', 'no_id_token', 'duplicate_kid',
                                 'private_jwk', 'unknown_kid', 'bad_signature', 'alg_none', 'oversize'])
def test_idp_failure_no_fallback_and_callback_cannot_retry(member, peer, mode):
    client = browser()
    url = begin(client)
    peer['mode'] = mode
    assert client.get(url)['Location'].endswith('result=failed')
    peer['mode'] = ''
    assert client.get(url)['Location'].endswith('result=failed')
    assert not SSOSession.objects.exists()
    # Local emergency login is independent of provider network availability.
    assert APIClient().post('/api/v1/auth/login/', {'username': member.username, 'password': PASSWORD}, format='json').status_code == 200


def test_email_collision_is_not_account_linking(peer):
    user = get_user_model().objects.create_user('unbound', email='same@example.com', password=PASSWORD)
    client = browser()
    assert client.get(begin(client))['Location'].endswith('result=failed')
    assert not ExternalIdentity.objects.filter(user=user).exists() and not SSOSession.objects.exists()


def test_browser_state_origin_and_expiry_are_checked_before_network(member, peer):
    first, other = browser(), browser()
    url = begin(first)
    assert other.get(url)['Location'].endswith('result=failed')
    assert len(peer['token_requests']) == 0
    assert first.get(url)['Location'].endswith('result=ready')
    no_origin = APIClient()
    assert no_origin.post(BASE + 'start/', {}, format='json').status_code == 403
    assert APIClient(HTTP_ORIGIN='https://evil.example').post(BASE + 'start/', {}, format='json').status_code == 403
    url = begin(first)
    LoginFlow.objects.filter(consumed_at__isnull=True).update(expires_at=timezone.now() - timedelta(seconds=1))
    count = len(peer['token_requests'])
    assert first.get(url)['Location'].endswith('result=failed') and len(peer['token_requests']) == count


@pytest.mark.parametrize('change', ['disabled', 'force_password', 'password', 'version', 'unbind', 'config'])
def test_local_changes_during_completion_invalidate_pending(member, peer, settings, change):
    client = browser()
    authorized(client)
    if change == 'disabled': get_user_model().objects.filter(pk=member.pk).update(is_active=False)
    elif change == 'force_password': get_user_model().objects.filter(pk=member.pk).update(must_change_password=True)
    elif change == 'password':
        member.set_password('Different-fixture#2026'); member.save(update_fields=['password'])
    elif change == 'version': get_user_model().objects.filter(pk=member.pk).update(session_version=1)
    elif change == 'unbind': ExternalIdentity.objects.update(revoked_at=timezone.now(), binding_version=2)
    else: settings.SSO_CLIENT_SECRET = 'rotated-secret'
    assert complete(client).status_code == 401
    assert not SSOSession.objects.exists()


def test_local_totp_required_consumed_once_and_recovery_codes_not_bypassed(member, peer, settings):
    settings.AUTH_TOTP_ENCRYPTION_KEY = Fernet.generate_key().decode()
    cipher = Fernet(settings.AUTH_TOTP_ENCRYPTION_KEY)
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    device = TOTPDevice.objects.create(user=member, active_secret=cipher.encrypt(secret.encode()).decode())
    client = browser(); authorized(client)
    assert client.get(BASE + 'status/').json()['data']['mfa_required'] is True
    assert complete(client).json()['data']['code'] == 'mfa_required'
    assert not SSOSession.objects.exists()
    code = hotp(secret, int(time.time() // 30))
    assert complete(client, otp_code=code).status_code == 200
    device.refresh_from_db(); assert device.last_counter >= 0
    again = browser(); authorized(again)
    assert complete(again, otp_code=code).status_code == 401


@pytest.mark.parametrize('change', ['module', 'config', 'identity', 'version', 'password'])
def test_sso_access_refresh_revocation_and_local_session_independence(member, peer, settings, change):
    client = browser(); authorized(client)
    pair = complete(client).json()['data']
    local = APIClient().post('/api/v1/auth/login/', {'username': member.username, 'password': PASSWORD}, format='json').json()
    if change == 'module': settings.ADMINCORE_MODULES = tuple(item for item in settings.ADMINCORE_MODULES if item != 'sso')
    elif change == 'config': settings.SSO_CLIENT_SECRET = 'rotated-secret'
    elif change == 'identity': ExternalIdentity.objects.update(revoked_at=timezone.now())
    elif change == 'version': get_user_model().objects.filter(pk=member.pk).update(session_version=1)
    else:
        member.set_password('Different-fixture#2026'); member.save(update_fields=['password'])
    authenticated = APIClient(); authenticated.credentials(HTTP_AUTHORIZATION='Bearer ' + pair['access'])
    assert authenticated.get('/api/v1/auth/me/').status_code == 401
    assert APIClient().post('/api/v1/auth/refresh/', {'refresh': pair['refresh']}, format='json').status_code == 400
    authenticated.credentials(HTTP_AUTHORIZATION='Bearer ' + local['access'])
    assert authenticated.get('/api/v1/auth/me/').status_code == (401 if change in {'version', 'password'} else 200)


def test_admin_explicit_binding_password_and_audit(member, peer):
    admin, client = local_admin()
    target = get_user_model().objects.create_user('binding-target', password=PASSWORD)
    draft = {'user_id': str(target.pk), 'subject': 'employee-002', 'current_password': PASSWORD}
    assert client.post(BASE + 'identities/', {**draft, 'current_password': 'wrong'}, format='json').status_code == 403
    assert client.post(BASE + 'identities/', {**draft, 'roles': ['admin']}, format='json').status_code == 400
    response = client.post(BASE + 'identities/', draft, format='json')
    assert response.status_code == 201, response.data
    assert not get_user_model().objects.get(pk=target.pk).is_staff
    row = response.json()['data']
    assert client.post(BASE + 'identities/', draft, format='json').status_code == 400
    assert client.post(BASE + f'identities/{row["id"]}/unbind/', {'current_password': PASSWORD}, format='json').status_code == 200
    assert ExternalIdentity.objects.get(pk=row['id']).revoked_at
    logs = OperationLog.objects.filter(resource='sso_identity', user=admin)
    assert logs.count() == 2
    assert 'employee-002' not in repr(list(logs.values())) and PASSWORD not in repr(list(logs.values()))
    client.credentials(HTTP_AUTHORIZATION='ApiToken fixture')
    assert client.get(BASE + 'identities/').status_code == 401


def test_only_admin_can_bind_even_with_role_permission(member, peer):
    from apps.permissions.models import Permission, Role, RolePermission, UserRole
    role = Role.objects.create(name='SSO delegated role')
    UserRole.objects.create(user=member, role=role)
    for action in ('read', 'bind', 'unbind'):
        permission = Permission.objects.create(resource='sso', action=action, code='sso:' + action, name=action)
        RolePermission.objects.create(role=role, permission=permission)
    client = APIClient()
    login = client.post('/api/v1/auth/login/', {'username': member.username, 'password': PASSWORD}, format='json').json()
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + login['access'])
    assert client.get(BASE + 'identities/').status_code == 403


def test_disabled_module_and_missing_config_are_closed(peer, settings):
    settings.SSO_CLIENT_SECRET = ''
    assert browser().get(BASE + 'config/').json()['data'] == {'enabled': False}
    assert browser().post(BASE + 'start/', {}, format='json').status_code == 503
    settings.ADMINCORE_MODULES = tuple(item for item in settings.ADMINCORE_MODULES if item != 'sso')
    assert browser().get(BASE + 'config/').status_code == 404


def test_cache_failure_and_public_rate_limit_fail_closed(peer):
    client = browser()
    with patch('apps.sso.service.cache.add', side_effect=RuntimeError('fixture')):
        assert client.post(BASE + 'start/', {}, format='json').status_code == 503
    for _ in range(20):
        assert client.post(BASE + 'start/', {}, format='json').status_code == 200
    assert client.post(BASE + 'start/', {}, format='json').status_code == 429


@pytest.mark.parametrize('field,value', [('SSO_ISSUER', 'http://idp.example'), ('SSO_TOKEN_ENDPOINT', 'https://other.example/token'),
    ('SSO_REDIRECT_URI', 'http://localhost:9000/callback/'), ('SSO_FRONTEND_ORIGIN', 'http://localhost:9000/evil'),
    ('SSO_ISSUER', 'https://127.0.0.1'), ('SSO_ISSUER', 'https://idp.example:444'),
    ('SSO_CLIENT_ID', 'bad\r\nid'), ('SSO_ENCRYPTION_KEY', 'bad')])
def test_config_rejects_untrusted_endpoints_and_bad_keys(peer, settings, field, value):
    setattr(settings, field, value)
    assert browser().get(BASE + 'config/').json()['data'] == {'enabled': False}


def test_loopback_test_exception_is_impossible_outside_testing(peer, settings):
    settings.TESTING = False
    with pytest.raises(SSOUnavailable): provider()


@pytest.mark.parametrize('other', ['AUTH_TOTP_ENCRYPTION_KEY', 'ADMINCORE_FIELD_ENCRYPTION_KEY', 'SECRET_KEY'])
def test_oidc_encryption_key_cannot_reuse_other_security_keys(peer, settings, other):
    setattr(settings, other, settings.SSO_ENCRYPTION_KEY)
    with pytest.raises(SSOUnavailable): provider()


def test_network_dns_private_pinning_no_proxy_and_tls_bypass(peer, settings):
    settings.SSO_TEST_ALLOW_LOOPBACK = False
    adapter = protocol.PinnedPublicAdapter()
    request = requests.Request('GET', 'https://idp.example/jwks').prepare()
    with patch('apps.sso.protocol.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
        with pytest.raises(SSOUnavailable): adapter.send(request)
    with pytest.raises(SSOUnavailable): adapter.send(request, verify=False)
    with pytest.raises(SSOUnavailable): adapter.send(request, proxies={'https': 'https://proxy.example'})
    with patch('apps.sso.protocol.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]), patch('apps.sso.protocol.DeadlineHTTPSConnection') as connection:
        received = connection.return_value.getresponse.return_value
        received.status = 200
        received.getheader.side_effect = lambda name, default='': 'application/json' if name == 'Content-Type' else default
        received.read.return_value = b'{}'
        received.getheaders.return_value = []
        adapter.send(request)
        assert connection.call_args.args[:2] == ('idp.example', 443)
        assert connection.return_value.request.call_args.kwargs['headers']['Host'] == 'idp.example'
        with patch('apps.sso.protocol.socket.socket') as raw:
            connection.return_value._create_connection(('idp.example', 443), 3)
            raw.return_value.connect.assert_called_once_with(('8.8.8.8', 443))
    adapter.close()


def test_pending_cookie_is_browser_bound_cancelled_and_expires(member, peer):
    client = browser(); authorized(client)
    assert browser().get(BASE + 'status/').status_code == 401
    assert client.post(BASE + 'cancel/', {}, format='json').status_code == 200
    assert complete(client).status_code == 401
    authorized(client)
    LoginFlow.objects.filter(completed_at__isnull=True).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert complete(client).status_code == 401
    assert not SSOSession.objects.exists()


def test_account_forced_password_or_disabled_before_callback_no_jwt(member, peer):
    client = browser(); url = begin(client)
    get_user_model().objects.filter(pk=member.pk).update(must_change_password=True)
    assert client.get(url)['Location'].endswith('result=failed')
    assert not SSOSession.objects.exists()


def test_audit_write_failure_rolls_back_session_and_totp_consumption(member, peer, settings):
    settings.AUTH_TOTP_ENCRYPTION_KEY = Fernet.generate_key().decode()
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    device = TOTPDevice.objects.create(user=member, active_secret=Fernet(settings.AUTH_TOTP_ENCRYPTION_KEY).encrypt(secret.encode()).decode())
    client = browser(); authorized(client)
    code = hotp(secret, int(time.time() // 30))
    with patch('apps.sso.service.OperationLog.objects.create', side_effect=RuntimeError('fixture audit unavailable')):
        assert complete(client, otp_code=code).status_code == 500
    assert not SSOSession.objects.exists() and not AuthSession.objects.filter(user=member).exists()
    device.refresh_from_db(); assert device.last_counter == -1
    assert complete(client, otp_code=code).status_code == 200


def test_bind_audit_failure_rolls_back_identity(member, peer):
    _, client = local_admin()
    target = get_user_model().objects.create_user('audit-target', password=PASSWORD)
    with patch('apps.sso.views.write_audit', side_effect=RuntimeError('fixture audit unavailable')):
        response = client.post(BASE + 'identities/', {'user_id': str(target.pk), 'subject': 'audit-subject', 'current_password': PASSWORD}, format='json')
    assert response.status_code == 500
    assert not ExternalIdentity.objects.filter(user=target).exists()


def test_successful_idp_check_still_requires_local_captcha_and_one_time_recovery(member, peer, settings):
    from apps.auth_app.login_captcha import record_failure
    from apps.auth_app.totp import recovery_hash
    settings.AUTH_LOGIN_CAPTCHA_ENABLED = True
    settings.AUTH_LOGIN_CAPTCHA_FAILURE_THRESHOLD = 3
    settings.AUTH_TOTP_ENCRYPTION_KEY = Fernet.generate_key().decode()
    secret, recovery = base64.b32encode(secrets.token_bytes(20)).decode(), secrets.token_hex(16)
    device = TOTPDevice.objects.create(user=member, active_secret=Fernet(settings.AUTH_TOTP_ENCRYPTION_KEY).encrypt(secret.encode()).decode(), recovery_hashes=[recovery_hash(recovery)])
    client = browser(); authorized(client)
    for _ in range(3): record_failure(client.get(BASE + 'status/').wsgi_request, member.username)
    result = complete(client, otp_code=recovery)
    assert result.status_code == 400 and result.json()['data']['code'] == 'captcha_required'
    device.refresh_from_db(); assert device.recovery_hashes == [recovery_hash(recovery)]
    # The shared captcha gate is exercised above; disable only the test gate to verify real recovery consumption.
    settings.AUTH_LOGIN_CAPTCHA_ENABLED = False
    assert complete(client, otp_code=recovery).status_code == 200
    device.refresh_from_db(); assert device.recovery_hashes == []
    authorized(client)
    assert complete(client, otp_code=recovery).status_code == 401


def test_callback_duplicate_query_and_cross_issuer_fail_before_token_exchange(member, peer):
    client = browser(); url = begin(client)
    assert client.get(url + '&state=duplicate')['Location'].endswith('result=failed')
    assert not peer['token_requests']
    parsed = urlsplit(url)
    query = parse_qs(parsed.query); query['iss'] = ['https://mixup.example']
    assert client.get(parsed.path + '?' + urlencode(query, doseq=True))['Location'].endswith('result=failed')
    assert not peer['token_requests']
    assert client.get(url)['Location'].endswith('result=failed')  # invalid callback cleared this browser's state cookie


def test_public_json_duplicate_members_rejected_before_token_parse():
    with pytest.raises(ValueError): protocol.unique_json('{"id_token":"first","id_token":"second"}')
    with pytest.raises(ValueError): protocol.unique_json('{"exp":NaN}')


def test_sso_flow_retention_batches_expired_and_runs_when_module_disabled(peer, settings):
    from apps.core.tasks import cleanup_expired_sessions
    now = timezone.now()
    rows = []
    for index, expiry in enumerate([now - timedelta(days=2), now - timedelta(days=2),
                                   now - timedelta(hours=23), now + timedelta(minutes=5)]):
        rows.append(LoginFlow.objects.create(state_digest=str(index), browser_digest='b', nonce_digest='n',
                    encrypted_verifier='fixture', config_digest='c', expires_at=expiry))
    settings.ADMINCORE_MODULES = tuple(item for item in settings.ADMINCORE_MODULES if item != 'sso')
    assert cleanup_expired_sessions(batch_size=1)['deleted_sso_flows'] == 1
    assert cleanup_expired_sessions(batch_size=1)['deleted_sso_flows'] == 1
    assert cleanup_expired_sessions()['deleted_sso_flows'] == 0
    assert set(LoginFlow.objects.values_list('pk', flat=True)) == {rows[2].pk, rows[3].pk}


def test_sso_flow_cleanup_rechecks_expiry_after_selection(peer):
    from apps.core.tasks import cleanup_expired_sessions
    from django.db.models.query import QuerySet
    row = LoginFlow.objects.create(state_digest='race', browser_digest='b', nonce_digest='n',
                                  encrypted_verifier='fixture', config_digest='c', expires_at=timezone.now() - timedelta(days=2))
    original = QuerySet.delete
    def renew_before_delete(queryset):
        if queryset.model is LoginFlow:
            LoginFlow.objects.filter(pk=row.pk).update(expires_at=timezone.now() + timedelta(minutes=5))
        return original(queryset)
    with patch.object(QuerySet, 'delete', renew_before_delete):
        assert cleanup_expired_sessions()['deleted_sso_flows'] == 0
    assert LoginFlow.objects.filter(pk=row.pk).exists()
