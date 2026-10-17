"""仅供隔离浏览器验收的 HTTPS OIDC 身份源；不记录查询、凭据或令牌。"""
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import ssl
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from joserfc import jwt
from joserfc.jwk import RSAKey


def main():
    if os.environ.get('DB_NAME') != 'browser_session_fixture':
        raise RuntimeError('OIDC fixture requires an isolated browser database')
    issuer = 'https://127.0.0.1:18494'
    callback = 'https://127.0.0.1:18493/api/v1/sso/callback/'
    key = RSAKey.generate_key(2048, parameters={'kid': 'browser-fixture'})
    pending, codes, lock = {}, {}, threading.Lock()
    counts = {'authorized': 0, 'cancelled': 0, 'exchanged': 0, 'jwks': 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, kind='application/json', location=None):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            if location:
                self.send_header('Location', location)
            self.end_headers()
            self.wfile.write(body)

        def json(self, value, status=200):
            self.reply(status, json.dumps(value).encode())

        def do_GET(self):
            parts = urlsplit(self.path)
            if parts.path == '/health':
                return self.json({'ready': True})
            if parts.path == '/summary':
                with lock:
                    return self.json(dict(counts))
            if parts.path == '/jwks':
                with lock:
                    counts['jwks'] += 1
                return self.json({'keys': [key.as_dict(private=False)]})
            if parts.path != '/authorize':
                return self.json({'error': 'not_found'}, 404)
            query = parse_qs(parts.query)
            expected = {'client_id': ['browser-fixture'], 'response_type': ['code'], 'scope': ['openid'],
                        'code_challenge_method': ['S256'], 'redirect_uri': [callback],
                        'max_age': ['300'], 'prompt': ['login']}
            if (any(query.get(name) != value for name, value in expected.items())
                    or any(len(query.get(name, [])) != 1 or not query[name][0]
                           for name in ('state', 'nonce', 'code_challenge'))):
                return self.json({'error': 'invalid_request'}, 400)
            ticket = secrets.token_urlsafe(24)
            with lock:
                pending[ticket] = (time.monotonic(), query)
            # 仅本地夹具身份选择；没有密码输入，也不展示协议令牌。
            html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>隔离身份源</title><h1>隔离身份源</h1>'
                    '<form method="post" action="/confirm">'
                    f'<input type="hidden" name="ticket" value="{ticket}">'
                    '<button name="subject" value="desktop">桌面验收成员</button>'
                    '<button name="subject" value="mobile">手机验收成员</button>'
                    '<button name="subject" value="unbound">未绑定成员</button>'
                    '<button name="subject" value="cancel">取消授权</button></form></html>')
            self.reply(200, html.encode(), 'text/html; charset=utf-8')

        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            if length > 8192:
                return self.json({'error': 'invalid_request'}, 400)
            params = parse_qs(self.rfile.read(length).decode())
            if self.path == '/confirm':
                with lock:
                    entry = pending.pop(params.get('ticket', [''])[0], None)
                subject = params.get('subject', [''])[0]
                if entry is None or time.monotonic() - entry[0] > 120 or subject not in {'desktop', 'mobile', 'unbound', 'cancel'}:
                    return self.json({'error': 'invalid_request'}, 400)
                query = entry[1]
                values = {'state': query['state'][0], 'iss': issuer}
                with lock:
                    if subject == 'cancel':
                        counts['cancelled'] += 1
                        values['error'] = 'access_denied'
                    else:
                        code = secrets.token_urlsafe(24)
                        codes[code] = (time.monotonic(), query, subject)
                        counts['authorized'] += 1
                        values['code'] = code
                return self.reply(302, b'', location=callback + '?' + urlencode(values))
            if self.path != '/token':
                return self.json({'error': 'not_found'}, 404)
            expected = 'Basic ' + base64.b64encode(('browser-fixture:' + os.environ['SSO_CLIENT_SECRET']).encode()).decode()
            if not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
                return self.json({'error': 'invalid_client'}, 401)
            with lock:
                entry = codes.pop(params.get('code', [''])[0], None)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(params.get('code_verifier', [''])[0].encode()).digest()).rstrip(b'=').decode()
            if (entry is None or time.monotonic() - entry[0] > 120
                    or entry[1]['code_challenge'] != [challenge] or params.get('redirect_uri') != [callback]
                    or params.get('grant_type') != ['authorization_code']):
                return self.json({'error': 'invalid_grant'}, 400)
            now = int(time.time())
            claims = {'iss': issuer, 'sub': entry[2], 'aud': 'browser-fixture', 'iat': now, 'exp': now + 300,
                      'auth_time': now, 'nonce': entry[1]['nonce'][0]}
            token = jwt.encode({'alg': 'RS256', 'kid': 'browser-fixture'}, claims, key)
            with lock:
                counts['exchanged'] += 1
            self.json({'id_token': token, 'token_type': 'Bearer', 'access_token': 'isolated-unused-token'})

    server = ThreadingHTTPServer(('0.0.0.0', 18494), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('/tmp/oidc-ca.crt', '/tmp/oidc.key')
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
