"""Real isolated TLS transport tests: deadlines apply even to slow headers / incomplete body chunks."""
import ssl
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from apps.sso import protocol
from apps.sso.configuration import SSOUnavailable


@contextmanager
def tls_peer(tmp_path, mode):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), False).sign(key, hashes.SHA256()))
    certificate, private_key = tmp_path / 'fixture-ca.pem', tmp_path / 'fixture-key.pem'
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                if mode == 'slow_headers':
                    for byte in b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 10000\r\n\r\n':
                        self.connection.sendall(bytes([byte])); time.sleep(0.05)
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', '10000' if mode == 'slow_body' else '2')
                    self.end_headers()
                    if mode == 'slow_body':
                        for _ in range(10000):
                            self.wfile.write(b' '); self.wfile.flush(); time.sleep(0.05)
                    elif mode == 'normal_delay':
                        time.sleep(0.22); self.wfile.write(b'{}')
                    else:
                        self.wfile.write(b'{}')
            except (OSError, ssl.SSLError):
                pass  # A successful deadline closes this connection while the peer is still dripping.

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(certificate), str(private_key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'https://localhost:{server.server_port}', certificate
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        # Only this fixture's ephemeral certificate/key are removed, never a caller's trust material.
        private_key.unlink(missing_ok=True); certificate.unlink(missing_ok=True)


@pytest.mark.parametrize('mode', ['slow_headers', 'slow_body'])
def test_tls_hard_deadline_interrupts_slow_trickle(tmp_path, settings, mode):
    settings.SSO_TEST_ALLOW_LOOPBACK = True
    context_factory = ssl.create_default_context
    with tls_peer(tmp_path, mode) as (url, certificate):
        with patch('apps.sso.protocol.LOGIN_NETWORK_SECONDS', 0.35), patch('apps.sso.protocol.ssl.create_default_context', side_effect=lambda: context_factory(cafile=str(certificate))):
            adapter = protocol.PinnedPublicAdapter()
            started = time.monotonic()
            with pytest.raises(SSOUnavailable): adapter.send(requests.Request('GET', url + '/jwks').prepare())
            assert time.monotonic() - started < 1.5
            adapter.close()


def test_tls_verifies_certificate_and_original_hostname(tmp_path, settings):
    settings.SSO_TEST_ALLOW_LOOPBACK = True
    context_factory = ssl.create_default_context
    with tls_peer(tmp_path, 'normal') as (url, certificate):
        # System trust rejects the fixture's self-signed certificate.
        with pytest.raises(SSOUnavailable): protocol.PinnedPublicAdapter().send(requests.Request('GET', url + '/jwks').prepare())
        with patch('apps.sso.protocol.ssl.create_default_context', side_effect=lambda: context_factory(cafile=str(certificate))):
            assert protocol.PinnedPublicAdapter().send(requests.Request('GET', url + '/jwks').prepare()).json() == {}
            # Explicit trust does not disable hostname checking: this certificate contains localhost, not its IP.
            with pytest.raises(SSOUnavailable): protocol.PinnedPublicAdapter().send(requests.Request('GET', url.replace('localhost', '127.0.0.1') + '/jwks').prepare())


def test_token_and_jwks_share_one_aggregate_deadline(tmp_path, settings):
    settings.SSO_TEST_ALLOW_LOOPBACK = True
    context_factory = ssl.create_default_context
    with tls_peer(tmp_path, 'normal_delay') as (url, certificate):
        with patch('apps.sso.protocol.LOGIN_NETWORK_SECONDS', 0.35), patch('apps.sso.protocol.ssl.create_default_context', side_effect=lambda: context_factory(cafile=str(certificate))):
            adapter = protocol.PinnedPublicAdapter()
            started = time.monotonic()
            assert adapter.send(requests.Request('GET', url + '/token-fixture').prepare()).json() == {}
            with pytest.raises(SSOUnavailable): adapter.send(requests.Request('GET', url + '/jwks').prepare())
            assert time.monotonic() - started < 1.5
            adapter.close()
