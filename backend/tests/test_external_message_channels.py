"""外部渠道的出站边界、已固定收件人、签名与不确定结果处理。"""
from copy import deepcopy
from datetime import timedelta
import json
import socket
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import MagicMock
from urllib.parse import parse_qs
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils import timezone

from apps.core.models import OutboxEvent
from apps.core.tasks import dispatch_outbox
from apps.notifications import external_channels as external
from apps.notifications.models import MessageDelivery
from tests.test_message_templates import template, send

pytestmark = pytest.mark.django_db
CONFIG = {'webhook': {'enabled': True, 'url': 'https://hooks.example.test/events',
    'active_key': 'current', 'keys': {'current': 'new-secret-' * 5, 'previous': 'old-secret-' * 5}},
    'sms': {'enabled': True, 'account_sid': 'AC' + '1' * 32, 'auth_token': 'private-' * 5,
            'from': '+14155550101', 'recipients': {}}}
REAL_SMS_FENCE = external.sms_fence


@pytest.fixture(autouse=True)
def sqlite_fence_double(monkeypatch):
    """SQLite 不支持独立 PG 事务；此处只测渠道逻辑，真实屏障由 PG 脚本验证。"""
    claimed = set()
    def fence(identifier, *, release=False):
        if release:
            claimed.discard(identifier)
            return True
        if identifier in claimed:
            return False
        claimed.add(identifier)
        return True
    monkeypatch.setattr(external, 'sms_fence', fence)


def configuration(user=None):
    result = deepcopy(CONFIG)
    if user:
        result['sms']['recipients'][str(user.pk)] = '+14155550102'
    return result


def fixture_delivery():
    return SimpleNamespace(pk=uuid4(), subject='Hello', body='Private text',
        version=SimpleNamespace(number=1, template=SimpleNamespace(code='fixture')))


@pytest.mark.parametrize('url', ['http://hooks.example.test', 'https://user:secret@host.test/',
    'https://host.test:8443/', 'https://host.test/?secret=x', 'https://host.test/#x',
    'https://[::1]/', 'https://host.test/\nattack', 'https://host.test/é'])
def test_config_rejects_url_before_any_network(url):
    cfg = configuration(); cfg['webhook']['url'] = url
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=cfg), patch.object(external.socket, 'getaddrinfo') as resolve:
        assert not external.enabled('webhook')
        with pytest.raises(ImproperlyConfigured): external.validate_configuration()
        resolve.assert_not_called()


def test_startup_disabled_defaults_and_invalid_enabled_keys():
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS={}):
        external.validate_configuration()
        assert not external.enabled('sms') and not external.enabled('webhook')
    for field, value in [('keys', {}), ('active_key', 'injected\nheader'), ('keys', {'current': 'short'})]:
        cfg = configuration(); cfg['webhook'][field] = value
        with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=cfg), pytest.raises(ImproperlyConfigured):
            external.validate_configuration()
    cfg = configuration(); cfg['sms']['recipients'] = {'not-a-user': '+14155550102'}
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=cfg), pytest.raises(ImproperlyConfigured):
        external.validate_configuration()


@pytest.mark.parametrize('addresses', [['127.0.0.1'], ['10.0.0.1'], ['169.254.169.254'],
    ['0.0.0.0'], ['::1'], ['::ffff:127.0.0.1'], ['100.64.0.1'], ['192.0.2.1'],
    ['8.8.8.8', '127.0.0.1'], []])
def test_dns_rejects_private_reserved_and_mixed_answers(addresses):
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in addresses]
    with patch.object(external.socket, 'getaddrinfo', return_value=answers):
        with pytest.raises(external.TerminalDeliveryError): external.public_address('fixture.test')


def test_dns_public_pinned_connection_keeps_tls_hostname_and_no_redirect():
    connection = SimpleNamespace(request=lambda *a, **k: None, getresponse=lambda: SimpleNamespace(status=302), close=lambda: None)
    with patch.object(external, 'public_address', return_value='8.8.8.8') as resolve, \
         patch.object(external.http.client, 'HTTPSConnection', return_value=connection) as connect, \
         patch.object(external.socket, 'create_connection', return_value='fixture-socket') as socket_connect:
        assert external.post('https://hooks.example.test/events', b'body', {}) == 302
        assert connect.call_args.args == ('hooks.example.test',)
        assert connect.call_args.kwargs['context'].check_hostname
        assert connection._create_connection(('rebound.test', 443), 5) == 'fixture-socket'
        assert socket_connect.call_args.args == (('8.8.8.8', 443),)
        resolve.assert_called_once_with('hooks.example.test')


def test_webhook_signature_rotation_replay_window_tamper_and_id_binding():
    row, user = fixture_delivery(), SimpleNamespace(pk=uuid4())
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration()), patch.object(external, 'post', return_value=204) as post:
        external.webhook(row, user)
        _, body, headers = post.call_args.args
        cache.clear()
        assert external.verify_webhook(body, headers, CONFIG['webhook']['keys'])
        assert not external.verify_webhook(body, headers, CONFIG['webhook']['keys'])
        cache.clear()
        assert not external.verify_webhook(body + b' ', headers, CONFIG['webhook']['keys'])
        assert not external.verify_webhook(body, headers, CONFIG['webhook']['keys'], now=int(headers['X-AdminCore-Timestamp']) + 301)
        wrong = {**headers, 'X-AdminCore-Event-Id': str(uuid4())}
        assert not external.verify_webhook(body, wrong, CONFIG['webhook']['keys'])
        assert json.loads(body)['recipient_id'] == str(user.pk)
        assert not any(secret in body.decode() + str(headers) for secret in CONFIG['webhook']['keys'].values())
        rotated = configuration(); rotated['webhook']['active_key'] = 'previous'
        with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=rotated): external.webhook(row, user)
        _, rotated_body, rotated_headers = post.call_args.args
        assert external.verify_webhook(rotated_body, rotated_headers, CONFIG['webhook']['keys'])


@pytest.mark.parametrize('status,error', [(302, external.TerminalDeliveryError), (400, external.TerminalDeliveryError),
    (401, external.TerminalDeliveryError), (429, external.RetryDeliveryError), (503, external.RetryDeliveryError)])
def test_webhook_rejection_policy(status, error):
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration()), patch.object(external, 'post', return_value=status):
        with pytest.raises(error): external.webhook(fixture_delivery(), SimpleNamespace(pk=uuid4()))


def test_twilio_exact_endpoint_form_and_provider_acceptance_only():
    user, row = SimpleNamespace(pk=uuid4()), fixture_delivery()
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration(user)), patch.object(external, 'post', return_value=201) as post:
        external.sms(row, user)
        url, body, headers = post.call_args.args
        assert url == 'https://api.twilio.com/2010-04-01/Accounts/AC' + '1' * 32 + '/Messages.json'
        assert parse_qs(body.decode()) == {'To': ['+14155550102'], 'From': ['+14155550101'], 'Body': ['Private text']}
        assert headers['Content-Type'] == 'application/x-www-form-urlencoded'
        assert headers['Authorization'].startswith('Basic ')


@pytest.mark.parametrize('outcome,error', [(429, external.RetryDeliveryError), (400, external.TerminalDeliveryError),
    (302, external.TerminalDeliveryError), (500, external.TerminalDeliveryError),
    (TimeoutError('private number secret'), external.TerminalDeliveryError)])
def test_sms_ambiguous_results_never_auto_retry(outcome, error):
    user = SimpleNamespace(pk=uuid4())
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration(user)), patch.object(external, 'post',
            **({'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome})):
        with pytest.raises(error): external.sms(fixture_delivery(), user)


def test_unregistered_sms_rejects_whole_batch_and_body_length(admin_client, member_user):
    identifier = template(admin_client).json()['data']['id']
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration()):
        assert send(admin_client, identifier, member_user, channels=['inapp', 'sms']).status_code == 400
        assert not MessageDelivery.objects.exists()
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration(member_user)):
        assert send(admin_client, identifier, member_user, channels=['sms'], values={'name': 'x' * 1600}).status_code == 400
        assert not MessageDelivery.objects.exists()


@pytest.mark.parametrize('channel', ['webhook', 'sms'])
def test_pipeline_external_changed_destination_terminates_before_network(admin_client, member_user, channel):
    identifier = template(admin_client).json()['data']['id']
    cfg = configuration(member_user)
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=cfg):
        assert send(admin_client, identifier, member_user, channels=[channel]).status_code == 202
    changed = deepcopy(cfg)
    if channel == 'sms': changed['sms']['recipients'][str(member_user.pk)] = '+14155550103'
    else: changed['webhook']['url'] = 'https://other.example.test/events'
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=changed), patch.object(external, 'post') as post:
        assert dispatch_outbox()['processed'] == 1
        post.assert_not_called()
    row = MessageDelivery.objects.get()
    assert row.status == 'terminated' and row.last_error == 'external_destination_changed' and row.attempts == 0
    assert member_user.phone not in str(row.__dict__) if member_user.phone else True


def test_sms_unknown_terminated_and_webhook_five_bounded_retries_no_secret(admin_client, member_user):
    identifier = template(admin_client).json()['data']['id']
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration(member_user)):
        assert send(admin_client, identifier, member_user, channels=['sms', 'webhook']).status_code == 202
        with patch.object(external, 'post', side_effect=TimeoutError('private-secret +14155550102')) as post:
            for attempt in range(5):
                OutboxEvent.objects.filter(topic='notification.delivery').update(available_at=timezone.now() - timedelta(seconds=1))
                dispatch_outbox()
            assert post.call_count == 6
        sms = MessageDelivery.objects.get(channel='sms'); hook = MessageDelivery.objects.get(channel='webhook')
        assert (sms.status, sms.attempts) == ('terminated', 1)
        assert (hook.status, hook.attempts) == ('failed', 5)
        assert 'private-secret' not in str(list(MessageDelivery.objects.values()))
        assert '+14155550102' not in str(list(MessageDelivery.objects.values()))
        assert not {'body', 'subject', 'external_binding'} & set(admin_client.get('/api/v1/notifications/deliveries/').json()['data']['items'][0])


def test_enabled_channels_and_batch_success_keep_existing_inapp(admin_client, member_user):
    identifier = template(admin_client).json()['data']['id']
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration(member_user)):
        channels = admin_client.get('/api/v1/notifications/templates/channels/').json()['data']
        assert {item['key'] for item in channels if item['enabled']} >= {'inapp', 'sms', 'webhook'}
        assert send(admin_client, identifier, member_user, channels=['inapp', 'sms', 'webhook']).status_code == 202
        with patch.object(external, 'post', side_effect=[204, 201]) as post:
            # 派发顺序由事件创建时间确定：inapp → sms → webhook。
            post.side_effect = lambda url, *args: 201 if 'twilio.com' in url else 204
            assert dispatch_outbox()['processed'] == 3
        assert list(MessageDelivery.objects.values_list('status', flat=True)) == ['succeeded'] * 3


def test_sms_fence_uses_separate_autocommit_connection_and_closes_on_failure():
    db = MagicMock(vendor='postgresql')
    isolated = db.copy.return_value
    cursor = isolated.cursor.return_value.__enter__.return_value
    cursor.rowcount = 1
    identifier = uuid4()
    with patch.object(external, 'connection', db):
        assert REAL_SMS_FENCE(identifier)
        isolated.set_autocommit.assert_called_once_with(True)
        assert cursor.execute.call_args.args[0].endswith('ON CONFLICT DO NOTHING')
        assert cursor.execute.call_args.args[1][0] == str(identifier)
        isolated.close.assert_called_once()
        isolated.reset_mock()
        cursor.execute.side_effect = RuntimeError('private database info')
        with pytest.raises(external.TerminalDeliveryError, match='sms_fence_unavailable'):
            REAL_SMS_FENCE(identifier)
        isolated.close.assert_called_once()


def test_sms_fence_survives_outer_delivery_rollback_and_stops_second_post():
    row, user = fixture_delivery(), SimpleNamespace(pk=uuid4())
    with override_settings(NOTIFICATION_EXTERNAL_CHANNELS=configuration(user)), patch.object(external, 'post', return_value=201) as post:
        external.sms(row, user)
        with pytest.raises(external.TerminalDeliveryError, match='sms_previous_outcome_unknown'):
            external.sms(row, user)
        post.assert_called_once()


def test_real_local_tls_post_validates_hostname_and_closes_fixture(tmp_path):
    """真实 TLS socket；只对本测试固定 DNS/端口和测试 CA，不放开生产安全策略。"""
    from datetime import datetime, timezone as datetime_timezone
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import ssl
    import threading
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Fixture')])
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
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('hooks.example.test')]), critical=False)
        .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / 'fixture.crt', tmp_path / 'fixture.key'
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    client_context = ssl.create_default_context(cafile=str(cert_path))
    captured = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append((self.headers['Host'], self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(204); self.end_headers()
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    original_connect = external.socket.create_connection
    def connect(address, timeout=None, source_address=None):
        assert address == ('127.0.0.1', 443)
        return original_connect(('127.0.0.1', server.server_port), timeout=timeout, source_address=source_address)
    try:
        with patch.object(external, 'public_address', return_value='127.0.0.1'), \
             patch.object(external.ssl, 'create_default_context', return_value=client_context), \
             patch.object(external.socket, 'create_connection', side_effect=connect):
            assert external.post('https://hooks.example.test/events', b'fixture', {}) == 204
            with pytest.raises(ssl.SSLCertVerificationError):
                external.post('https://wrong.example.test/events', b'fixture', {})
        assert captured == [('hooks.example.test', b'fixture')]
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=5)
        assert not worker.is_alive()
        cert_path.unlink(); key_path.unlink()
