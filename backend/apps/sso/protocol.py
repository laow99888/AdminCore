"""Bounded OAuth code exchange + explicit OIDC claim validation. No IdP token is retained."""
import base64
import hmac
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import BoundedSemaphore, Timer
from urllib.parse import urlsplit

from authlib.integrations.requests_client import OAuth2Session
from joserfc import jwt
from joserfc.jwk import KeySet
from requests import Response
from requests.adapters import BaseAdapter

from .configuration import SSOUnavailable, digest, loopback_allowed

_resolver = ThreadPoolExecutor(max_workers=4, thread_name_prefix='sso-dns')
_resolver_slots = BoundedSemaphore(4)
LOGIN_NETWORK_SECONDS = 15


def public_addresses(host, port, timeout=3):
    # DNS resolution is not covered by Requests' connect timeout. Bound both elapsed wait and concurrent work.
    if timeout <= 0 or not _resolver_slots.acquire(blocking=False):
        raise SSOUnavailable()
    try:
        future = _resolver.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    except Exception:
        _resolver_slots.release()
        raise SSOUnavailable() from None
    future.add_done_callback(lambda _: _resolver_slots.release())
    try:
        addresses = sorted({item[4][0] for item in future.result(timeout=min(3, timeout))})
        if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
            raise ValueError()
        return addresses
    except (FutureTimeout, OSError, ValueError):
        raise SSOUnavailable() from None


def unique_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError('duplicate JSON member')
            result[key] = item
        return result
    return json.loads(value, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


class DeadlineHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        # Publish the TLS socket before the handshake so the hard deadline can interrupt it too.
        http.client.HTTPConnection.connect(self)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host, do_handshake_on_connect=False)
        self.deadline_socket = self.sock
        if time.monotonic() >= self.deadline_at:
            raise SSOUnavailable()
        self.sock.do_handshake()


class PinnedPublicAdapter(BaseAdapter):
    """One aggregate hard deadline covers DNS + connect + TLS + headers + bodies of BOTH protocol calls."""
    def __init__(self):
        self.deadline_at = time.monotonic() + LOGIN_NETWORK_SECONDS

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        if proxies or verify is not True or cert is not None:
            raise SSOUnavailable()
        parts = urlsplit(request.url)
        testing_loopback = loopback_allowed(request.url)
        if parts.scheme != 'https' and not (testing_loopback and parts.scheme == 'http'):
            raise SSOUnavailable()
        host, port = parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80)
        address = host if testing_loopback else public_addresses(host, port, self.deadline_at - time.monotonic())[0]
        remaining = self.deadline_at - time.monotonic()
        if remaining <= 0:
            raise SSOUnavailable()
        if parts.scheme == 'https':
            connection = DeadlineHTTPSConnection(host, port, timeout=min(3, remaining), context=ssl.create_default_context())
            connection.deadline_at = self.deadline_at
        else:
            connection = http.client.HTTPConnection(host, port, timeout=min(3, remaining))
        socket_holder = {}

        def connect_pinned(target, timeout, source_address=None):
            family = socket.AF_INET6 if ':' in address else socket.AF_INET
            raw = socket.socket(family, socket.SOCK_STREAM)
            socket_holder['socket'] = raw
            raw.settimeout(timeout)
            if time.monotonic() >= self.deadline_at:
                raw.close()
                raise SSOUnavailable()
            raw.connect((address, port))
            return raw

        connection._create_connection = connect_pinned

        def expire():
            for current in (connection.sock, getattr(connection, 'deadline_socket', None), socket_holder.get('socket'), socket_holder.get('connected')):
                if current is not None:
                    try:
                        current.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    try:
                        current.close()
                    except OSError:
                        pass

        remaining = self.deadline_at - time.monotonic()
        if remaining <= 0:
            connection.close()
            raise SSOUnavailable()
        deadline = Timer(remaining, expire)
        deadline.daemon = True
        deadline.start()
        received = None
        try:
            headers = dict(request.headers)
            headers['Host'] = parts.netloc
            headers['Accept-Encoding'] = 'identity'
            connection.request(request.method, parts.path or '/', body=request.body, headers=headers)
            socket_holder['connected'] = connection.sock
            received = connection.getresponse()
            if (received.status != 200 or received.getheader('Content-Type', '').split(';')[0].strip().lower() not in {'application/json', 'application/jwk-set+json'}
                    or received.getheader('Content-Encoding', 'identity').lower() not in {'identity', ''}):
                raise SSOUnavailable()
            body = received.read(65537)
            if len(body) > 65536 or time.monotonic() >= self.deadline_at or not isinstance(unique_json(body), dict):
                raise SSOUnavailable()
            response = Response()
            response.status_code, response.url, response.request = received.status, request.url, request
            response.headers.update(dict(received.getheaders()))
            response._content, response._content_consumed = body, True
            return response
        except Exception:
            raise SSOUnavailable() from None
        finally:
            deadline.cancel()
            if received is not None:
                received.close()
            connection.close()
            tls_socket = getattr(connection, 'deadline_socket', None)
            if tls_socket is not None:
                tls_socket.close()
            raw = socket_holder.get('socket')
            if raw is not None:
                raw.close()

    def close(self):
        pass  # Every request owns and closes its socket; no reusable pool survives the hard deadline.


def client(config):
    result = OAuth2Session(config.client_id, config.client_secret, scope='openid',
        redirect_uri=config.redirect_uri, token_endpoint_auth_method='client_secret_basic', code_challenge_method='S256')
    result.trust_env = False
    adapter = PinnedPublicAdapter()
    result.mount('https://', adapter)
    result.mount('http://', adapter)
    return result


def authorization_url(config, state, nonce, verifier):
    with client(config) as session:
        url, _ = session.create_authorization_url(config.authorization_endpoint, state=state,
            nonce=nonce, code_verifier=verifier, response_mode='query', max_age=300, prompt='login')
        return url


def verified_subject(config, code, verifier, nonce_digest):
    try:
        with client(config) as session:
            token = session.fetch_token(config.token_endpoint, code=code, code_verifier=verifier,
                grant_type='authorization_code', timeout=(3, 5), allow_redirects=False, stream=True)
            encoded = token.get('id_token')
            if (not isinstance(encoded, str) or len(encoded) > 16384 or token.get('token_type', '').lower() != 'bearer'
                    or not isinstance(token.get('access_token'), str) or not token['access_token']):
                raise ValueError()
            parts = encoded.split('.')
            if len(parts) != 3:
                raise ValueError()
            header, claims = [unique_json(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))) for part in parts[:2]]
            if not isinstance(header, dict) or not isinstance(claims, dict) or header.get('alg') != 'RS256' or set(header) - {'alg', 'kid', 'typ'}:
                raise ValueError()
            kid = header.get('kid')
            if not isinstance(kid, str) or not 1 <= len(kid) <= 128:
                raise ValueError()
            # OAuth client must not attach the just-issued access token to the JWKS endpoint.
            response = session.get(config.jwks_uri, withhold_token=True, timeout=(3, 5), allow_redirects=False, stream=True)
            keys = unique_json(response.content).get('keys')
            if not isinstance(keys, list) or not 1 <= len(keys) <= 10:
                raise ValueError()
            matches = [key for key in keys if isinstance(key, dict) and key.get('kid') == kid]
            if len(matches) != 1:
                raise ValueError()
            key = matches[0]
            if (key.get('kty') != 'RSA' or key.get('use', 'sig') != 'sig' or key.get('alg', 'RS256') != 'RS256'
                    or set(key) - {'kty', 'kid', 'use', 'alg', 'n', 'e', 'x5c', 'x5t', 'x5t#S256', 'key_ops'}
                    or ('key_ops' in key and key['key_ops'] != ['verify'])):
                raise ValueError()
            decoded = jwt.decode(encoded, KeySet.import_key_set({'keys': [key]}), algorithms=['RS256'])
            claims = decoded.claims
            now = time.time()
            for field in ('exp', 'iat', 'auth_time'):
                if type(claims.get(field)) not in (int, float):
                    raise ValueError()
            audience = claims.get('aud')
            if isinstance(audience, str):
                audience = [audience]
            if (not isinstance(audience, list) or not audience or not all(isinstance(item, str) for item in audience)
                    or config.client_id not in audience or len(set(audience)) != len(audience)
                    or (len(audience) > 1 and claims.get('azp') != config.client_id)
                    or ('azp' in claims and claims['azp'] != config.client_id)
                    or claims.get('iss') != config.issuer or claims['exp'] <= now - 30
                    or claims['iat'] > now + 30 or claims['iat'] < now - 600
                    or claims['auth_time'] > now + 30 or claims['auth_time'] < now - 330
                    or claims['exp'] <= claims['iat'] or claims['exp'] - claims['iat'] > 3600
                    or ('nbf' in claims and (type(claims['nbf']) not in (int, float) or claims['nbf'] > now + 30))
                    or not isinstance(claims.get('nonce'), str)
                    or not hmac.compare_digest(digest(claims['nonce']), nonce_digest)
                    or not isinstance(claims.get('sub'), str) or not re.fullmatch(r'[\x21-\x7e]{1,255}', claims['sub'])):
                raise ValueError()
            return claims['sub']
    except Exception:
        # Never propagate provider responses, authorization codes, tokens, URL parameters or client secrets.
        raise SSOUnavailable() from None
