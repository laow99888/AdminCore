"""仅 foundation PostgreSQL：真实本地 TLS 对端，不连接 Twilio 或公网 Webhook。

此脚本刻意仅在夹具上下文替换 DNS/端口与 CA；生产代码没有私网或跳过证书开关。
"""
from datetime import datetime, timedelta, timezone as datetime_timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import override_settings
from rest_framework.test import APIClient

from apps.notifications import external_channels as external
from apps.notifications.message_services import deliver
from apps.notifications.models import MessageDelivery, SmsDispatchFence

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connection.vendor == 'postgresql', '必须使用 PostgreSQL'
captures = []
statuses = {'hook': [503, 204], 'sms': [429, 201, 201, 201]}
fences = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        assert 0 < length <= 100000
        body = self.rfile.read(length)
        kind = 'sms' if self.path.endswith('/Messages.json') else 'hook'
        captures.append((kind, body, dict(self.headers)))
        status = statuses[kind].pop(0)
        self.send_response(status)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, *_):
        pass


class RollbackAcceptedSms(Exception):
    pass


with tempfile.TemporaryDirectory(prefix='admincore-notification-tls-') as directory:
    root = Path(directory)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'AdminCore isolated fixture')])
    now = datetime.now(datetime_timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('hooks.example.test'),
            x509.DNSName('api.twilio.com')]), critical=False)
        .sign(key, hashes.SHA256()))
    cert_path, key_path = root / 'fixture.crt', root / 'fixture.key'
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    client_context = ssl.create_default_context(cafile=str(cert_path))
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, name='notification-tls-fixture', daemon=True)
    thread.start()
    original_connect = external.socket.create_connection
    def fixture_connect(address, timeout=None, source_address=None):
        assert address == ('127.0.0.1', 443), '夹具拒绝其他出站地址'
        return original_connect(('127.0.0.1', server.server_port), timeout=timeout, source_address=source_address)
    try:
        user = get_user_model().objects.get(username='admin')
        config = {'webhook': {'enabled': True, 'url': 'https://hooks.example.test/events',
            'active_key': 'fixture', 'keys': {'fixture': 'isolated-test-key-' * 3}},
            'sms': {'enabled': True, 'account_sid': 'AC' + '1' * 32, 'auth_token': 'isolated-token-' * 3,
                    'from': '+14155550101', 'recipients': {str(user.pk): '+14155550102'}}}
        client = APIClient(HTTP_HOST='localhost'); client.force_authenticate(user)
        with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=config), \
             patch.object(external, 'public_address', return_value='127.0.0.1'), \
             patch.object(external.ssl, 'create_default_context', return_value=client_context), \
             patch.object(external.socket, 'create_connection', side_effect=fixture_connect):
            with transaction.atomic():
                response = client.post('/api/v1/notifications/templates/', {'code': 'external-fixture-' + uuid4().hex[:8],
                    'name': 'Isolated TLS fixture', 'revision': 0, 'enabled': True,
                    'subject': 'Private fixture', 'body': 'Private text', 'variables': []}, format='json')
                assert response.status_code == 201
                identifier = response.json()['data']['id']
                response = client.post('/api/v1/notifications/templates/' + identifier + '/send/',
                    {'revision': 1, 'recipient_ids': [str(user.pk)], 'channels': ['webhook', 'sms'], 'values': {}},
                    format='json', HTTP_IDEMPOTENCY_KEY=uuid4().hex)
                assert response.status_code == 202
                rows = list(MessageDelivery.objects.filter(pk__in=response.json()['data']['delivery_ids']))
                for row in rows:
                    fences.append(row.pk)
                    assert deliver({'delivery_id': str(row.pk)}) is True
                    assert deliver({'delivery_id': str(row.pk)}) is False
                    row.refresh_from_db()
                    assert row.status == 'succeeded' and row.attempts == 2
                assert len(captures) == 4
                hook = next(item for item in captures if item[0] == 'hook')
                replay_namespace = 'external-fixture-' + uuid4().hex
                assert external.verify_webhook(hook[1], hook[2], config['webhook']['keys'], namespace=replay_namespace)
                assert not external.verify_webhook(hook[1], hook[2], config['webhook']['keys'], namespace=replay_namespace)
                print('通过：真实本地 TLS Webhook 签名、防重放、503 后同事件重试；未连接公网', flush=True)
                print('通过：真实本地 TLS Twilio 协议适配、429 安全重试、201 仅视为供应商接收', flush=True)

                response = client.post('/api/v1/notifications/templates/' + identifier + '/send/',
                    {'revision': 1, 'recipient_ids': [str(user.pk)], 'channels': ['sms'], 'values': {}},
                    format='json', HTTP_IDEMPOTENCY_KEY=uuid4().hex)
                assert response.status_code == 202
                sms_id = response.json()['data']['delivery_ids'][0]; fences.append(sms_id)
                try:
                    with transaction.atomic():
                        assert deliver({'delivery_id': sms_id}) is False
                        raise RollbackAcceptedSms()
                except RollbackAcceptedSms:
                    pass
                row = MessageDelivery.objects.get(pk=sms_id)
                assert row.attempts == 0 and row.status == 'pending'
                assert SmsDispatchFence.objects.filter(pk=sms_id).exists()
                count = len(captures)
                assert deliver({'delivery_id': sms_id}) is False
                row.refresh_from_db()
                assert row.status == 'terminated' and len(captures) == count
                print('通过：真实 PostgreSQL 外层回滚不抹除独立短信意图；恢复后禁止重复 POST', flush=True)

                response = client.post('/api/v1/notifications/templates/' + identifier + '/send/',
                    {'revision': 1, 'recipient_ids': [str(user.pk)], 'channels': ['sms'], 'values': {}},
                    format='json', HTTP_IDEMPOTENCY_KEY=uuid4().hex)
                assert response.status_code == 202
                sms_id = response.json()['data']['delivery_ids'][0]; fences.append(sms_id)
                # 子进程真实 TLS POST 得到 201 后硬退出；不运行任何 finally/退出钩子。
                # 投递行在父事务中尚未提交，故子进程仅用相同 UUID 测试供应商边界。
                program = '''
import json, os, ssl, sys
from types import SimpleNamespace
from unittest.mock import patch
from django.test import override_settings
from apps.notifications import external_channels as external
data = json.load(sys.stdin)
context = ssl.create_default_context(cafile=data['ca'])
original = external.socket.create_connection
def connect(address, timeout=None, source_address=None):
    assert address == ('127.0.0.1', 443)
    return original(('127.0.0.1', data['port']), timeout=timeout, source_address=source_address)
row = SimpleNamespace(pk=data['delivery'], body='Private text')
user = SimpleNamespace(pk=data['recipient'])
with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=data['config']), patch.object(external, 'public_address', return_value='127.0.0.1'), patch.object(external.ssl, 'create_default_context', return_value=context), patch.object(external.socket, 'create_connection', side_effect=connect):
    external.sms(row, user)
    os._exit(91)
'''
                count = len(captures)
                child = subprocess.run([sys.executable, 'manage.py', 'shell', '-c', program],
                    input=json.dumps({'config': config, 'ca': str(cert_path), 'port': server.server_port,
                                      'delivery': sms_id, 'recipient': str(user.pk)}),
                    text=True, encoding='utf-8', capture_output=True, timeout=30)
                assert child.returncode == 91, '短信硬退子进程未到达预定退出点：' + child.stderr
                assert len(captures) == count + 1
                assert SmsDispatchFence.objects.filter(pk=sms_id).exists()
                assert deliver({'delivery_id': sms_id}) is False
                row = MessageDelivery.objects.get(pk=sms_id)
                assert row.status == 'terminated' and row.attempts == 1 and len(captures) == count + 1
                print('通过：真实子进程在 TLS 对端接收后 os._exit 硬退；恢复读取持久屏障且未重复 POST', flush=True)
                transaction.set_rollback(True)
        print('通过：本段模板、投递、事件夹具事务回滚', flush=True)
    finally:
        # 意图不属于外层事务，只删除本脚本记录的 UUID；保留正式/其他阶段数据。
        SmsDispatchFence.objects.filter(pk__in=fences).delete()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()
print('通过：本段 TLS 服务、随机端口、测试证书与短信意图夹具清理', flush=True)
