"""manage.py shell fixture: actual foundation PostgreSQL + isolated HTTP OIDC/RSA, never a real vendor tenant."""
import base64
import hashlib
import json
import secrets
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import override_settings
from django.urls import include, path
from joserfc import jwt
from joserfc.jwk import RSAKey
from rest_framework.test import APIClient

from apps.logs.models import LoginLog, OperationLog
from apps.sso.configuration import digest
from apps.sso.models import ExternalIdentity, LoginFlow, SSOSession

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connection.vendor == 'postgresql', '必须使用 PostgreSQL'
assert not connection.in_atomic_block, '并发夹具必须使用独立提交，不能包裹外层事务'
BASE, ORIGIN = '/api/v1/sso/', 'http://localhost:9000'
key = RSAKey.generate_key(2048, parameters={'kid': 'isolated-pg-key'})
codes, code_lock, token_exchanges = {}, threading.Lock(), []


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value, status=200):
        content = json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content))); self.end_headers(); self.wfile.write(content)

    def do_GET(self):
        if self.path == '/jwks':
            assert not self.headers.get('Authorization'), '不得向 JWKS 泄露 access token'
            return self.reply({'keys': [key.as_dict(private=False)]})
        parsed = urlsplit(self.path)
        assert parsed.path == '/authorize'
        query = parse_qs(parsed.query)
        assert query['client_id'] == ['pg-fixture-client'] and query['response_type'] == ['code']
        assert query['scope'] == ['openid'] and query['code_challenge_method'] == ['S256']
        assert query['max_age'] == ['300'] and query['prompt'] == ['login']
        assert query['redirect_uri'] == [ORIGIN + BASE + 'callback/']
        code = secrets.token_urlsafe(24)
        with code_lock: codes[code] = query
        self.send_response(302)
        self.send_header('Location', query['redirect_uri'][0] + '?' + urlencode({'code': code, 'state': query['state'][0], 'iss': issuer}))
        self.end_headers()

    def do_POST(self):
        assert self.path == '/token'
        assert self.headers['Authorization'] == 'Basic ' + base64.b64encode(b'pg-fixture-client:pg-fixture-secret').decode()
        data = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
        with code_lock:
            original = codes.pop(data.get('code', [''])[0], None)
            token_exchanges.append(True)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(data.get('code_verifier', [''])[0].encode()).digest()).rstrip(b'=').decode()
        if original is None or original['code_challenge'] != [challenge] or data.get('redirect_uri') != original['redirect_uri']:
            return self.reply({'error': 'invalid_grant'}, 400)
        now = int(time.time())
        claims = {'iss': issuer, 'sub': 'pg-employee-' + suffix, 'aud': 'pg-fixture-client', 'iat': now,
                  'exp': now + 300, 'auth_time': now, 'nonce': original['nonce'][0]}
        self.reply({'id_token': jwt.encode({'alg': 'RS256', 'kid': 'isolated-pg-key'}, claims, key),
                    'access_token': 'isolated-provider-token', 'token_type': 'Bearer'})


url_name = 'admincore_sso_pg_validation_urls'
urls = types.ModuleType(url_name)
urls.urlpatterns = [path('api/v1/sso/', include('apps.sso.urls')), path('api/v1/auth/', include('apps.auth_app.urls'))]
assert url_name not in sys.modules
sys.modules[url_name] = urls
suffix, password = uuid4().hex[:12], secrets.token_urlsafe(32)
fixture_ip = f'198.18.{int(suffix[:4], 16) % 256}.{int(suffix[4:8], 16) % 254 + 1}'
user_ids, identity_ids, flow_ids = [], [], []
server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
issuer = f'http://127.0.0.1:{server.server_port}'
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()


def check(label, value):
    assert value, label
    print('通过：' + label, flush=True)


def browser(cookies=None):
    value = APIClient(HTTP_HOST='localhost', HTTP_ORIGIN=ORIGIN, REMOTE_ADDR=fixture_ip)
    if cookies:
        value.cookies.update(cookies)
    return value


def parallel_request(method, url, cookies):
    barrier = threading.Barrier(2)
    def execute(_):
        close_old_connections()
        try:
            client = browser(cookies)
            barrier.wait(timeout=10)
            response = client.get(url) if method == 'GET' else client.post(url, {}, format='json')
            return response.status_code, response.get('Location', ''), response.json() if method == 'POST' else None, client.cookies
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as workers:
        return list(workers.map(execute, range(2)))


try:
    with override_settings(ROOT_URLCONF=url_name, TESTING=True, SSO_TEST_ALLOW_LOOPBACK=True,
            AUTH_LOGIN_CAPTCHA_ENABLED=False, SSO_ISSUER=issuer, SSO_AUTHORIZATION_ENDPOINT=issuer + '/authorize',
            SSO_TOKEN_ENDPOINT=issuer + '/token', SSO_JWKS_URI=issuer + '/jwks', SSO_CLIENT_ID='pg-fixture-client',
            SSO_CLIENT_SECRET='pg-fixture-secret', SSO_ENCRYPTION_KEY=Fernet.generate_key().decode(),
            SSO_FRONTEND_ORIGIN=ORIGIN, SSO_REDIRECT_URI=ORIGIN + BASE + 'callback/', SSO_SESSION_SECONDS=3600,
            ADMINCORE_MODULES=tuple(dict.fromkeys((*settings.ADMINCORE_MODULES, 'sso')))):
        admin = get_user_model().objects.create_superuser('sso_admin_' + suffix, password=password)
        user_ids.append(admin.pk)
        member = get_user_model().objects.create_user('sso_member_' + suffix, password=password)
        user_ids.append(member.pk)
        manager = browser()
        login = manager.post('/api/v1/auth/login/', {'username': admin.username, 'password': password}, format='json')
        check('SSO PostgreSQL 管理员使用真实本地 JWT 登录', login.status_code == 200)
        manager.credentials(HTTP_AUTHORIZATION='Bearer ' + login.json()['access'])
        bound = manager.post(BASE + 'identities/', {'user_id': str(member.pk), 'subject': 'pg-employee-' + suffix,
                            'current_password': password}, format='json')
        check('SSO PostgreSQL 仅显式密码确认绑定既有账号', bound.status_code == 201)
        identifier = bound.json()['data']['id']; identity_ids.append(identifier)
        local = browser().post('/api/v1/auth/login/', {'username': member.username, 'password': password}, format='json').json()

        client = browser()
        started = client.post(BASE + 'start/', {}, format='json')
        check('SSO PostgreSQL 建立浏览器绑定 state/nonce/PKCE', started.status_code == 200)
        authorization_url = started.json()['data']['authorization_url']
        state_value = parse_qs(urlsplit(authorization_url).query)['state'][0]
        flow_ids.append(LoginFlow.objects.get(state_digest=digest(state_value)).pk)
        with requests.Session() as session:
            session.trust_env = False
            authorization = session.get(authorization_url, allow_redirects=False, timeout=5)
        check('隔离 OIDC 对端执行真实授权码流程（并非真实企业供应商）', authorization.status_code == 302)
        callbacks = parallel_request('GET', authorization.headers['Location'], client.cookies.copy())
        ready = [item for item in callbacks if item[1].endswith('result=ready')]
        check('SSO PostgreSQL 两线程争用同一 state 仅兑换一次授权码', len(ready) == 1 and len(token_exchanges) == 1)
        check('SSO PostgreSQL 授权前后不提前签发企业会话', not SSOSession.objects.filter(identity_id=identifier).exists())
        completed = parallel_request('POST', BASE + 'complete/', ready[0][3].copy())
        success = [item for item in completed if item[0] == 200]
        check('SSO PostgreSQL 两线程争用同一完成凭据仅签发一个会话', len(success) == 1 and sorted(item[0] for item in completed) == [200, 401]
              and SSOSession.objects.filter(identity_id=identifier).count() == 1)
        pair = success[0][2]['data']
        signed = browser(); signed.credentials(HTTP_AUTHORIZATION='Bearer ' + pair['access'])
        check('SSO PostgreSQL 完整 code+PKCE+nonce+RS256 后 JWT 可用', signed.get('/api/v1/auth/me/').status_code == 200)
        revoked = manager.post(BASE + f'identities/{identifier}/unbind/', {'current_password': password}, format='json')
        check('SSO PostgreSQL 解绑立即撤销旧企业 access 与 refresh', revoked.status_code == 200
              and signed.get('/api/v1/auth/me/').status_code == 401
              and browser().post('/api/v1/auth/refresh/', {'refresh': pair['refresh']}, format='json').status_code == 400)
        signed.credentials(HTTP_AUTHORIZATION='Bearer ' + local['access'])
        check('SSO PostgreSQL 企业绑定撤销保留独立本地应急会话', signed.get('/api/v1/auth/me/').status_code == 200)
finally:
    server.shutdown(); server.server_close(); server_thread.join(timeout=5)
    # Only this fixture's tracked records are removed; the dedicated foundation database is never flushed.
    LoginFlow.objects.filter(pk__in=flow_ids).delete()
    OperationLog.objects.filter(user_id__in=user_ids).delete()
    LoginLog.objects.filter(user_id__in=user_ids).delete()
    LoginLog.objects.filter(username='[SSO]', ip_address=fixture_ip).delete()
    ExternalIdentity.objects.filter(pk__in=identity_ids).delete()
    get_user_model().objects.filter(pk__in=user_ids).delete()
    sys.modules.pop(url_name, None)
    check('SSO PostgreSQL 隔离身份/会话/账号夹具已清理，对端线程已停止', not get_user_model().objects.filter(pk__in=user_ids).exists() and not server_thread.is_alive())
