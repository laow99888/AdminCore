"""A single operator-configured provider; no discovery, dynamic registration or request-controlled URLs."""
import hashlib
import ipaddress
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from django.conf import settings
from rest_framework.exceptions import APIException


class SSOUnavailable(APIException):
    status_code = 503
    default_detail = '企业登录暂不可用，请使用本地登录或联系管理员'
    default_code = 'sso_unavailable'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def loopback_allowed(url):
    parsed = urlsplit(url)
    return bool(getattr(settings, 'TESTING', False) and getattr(settings, 'SSO_TEST_ALLOW_LOOPBACK', False)
                and parsed.hostname in {'localhost', '127.0.0.1', '::1'})


def checked_url(value, *, callback=False):
    if not isinstance(value, str) or len(value) > 512 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise SSOUnavailable()
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query
                or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and loopback_allowed(value)))
                or (port is not None and port != 443 and not loopback_allowed(value))):
            raise ValueError()
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global and not loopback_allowed(value):
            raise ValueError()
        if callback and parsed.path != '/api/v1/sso/callback/':
            raise ValueError()
    except (ValueError, TypeError):
        raise SSOUnavailable() from None
    return value


@dataclass(frozen=True)
class Provider:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    client_id: str
    client_secret: str
    redirect_uri: str
    frontend_origin: str
    label: str
    session_seconds: int
    encryption_key: str

    @property
    def fingerprint(self):
        values = self.__dict__.copy()
        values['client_secret'] = digest(self.client_secret)
        values['encryption_key'] = digest(self.encryption_key)
        return digest(json.dumps(values, sort_keys=True))

    @property
    def cipher(self):
        try:
            return Fernet(self.encryption_key.encode())
        except (TypeError, ValueError):
            raise SSOUnavailable() from None


def provider():
    try:
        values = {field: getattr(settings, 'SSO_' + field.upper(), '') for field in (
            'issuer', 'authorization_endpoint', 'token_endpoint', 'jwks_uri', 'client_id', 'client_secret',
            'redirect_uri', 'frontend_origin', 'encryption_key')}
        for name in ('issuer', 'authorization_endpoint', 'token_endpoint', 'jwks_uri', 'redirect_uri', 'frontend_origin'):
            checked_url(values[name], callback=name == 'redirect_uri')
        # All protocol endpoints must share the configured issuer origin; cross-origin discovery is unsupported.
        origin = lambda value: (urlsplit(value).scheme, urlsplit(value).netloc)
        if any(origin(values[name]) != origin(values['issuer']) for name in ('authorization_endpoint', 'token_endpoint', 'jwks_uri')):
            raise ValueError()
        frontend = urlsplit(values['frontend_origin'])
        if frontend.path or values['frontend_origin'].endswith('/'):
            raise ValueError()
        # Cookies and public API calls require the same site/origin deployment used by this scaffold.
        if origin(values['redirect_uri']) != origin(values['frontend_origin']):
            raise ValueError()
        for name in ('client_id', 'client_secret'):
            if not isinstance(values[name], str) or not 1 <= len(values[name]) <= 2048 or any(ord(c) < 33 for c in values[name]):
                raise ValueError()
        seconds = getattr(settings, 'SSO_SESSION_SECONDS', 3600)
        label = getattr(settings, 'SSO_LABEL', '企业身份登录')
        if type(seconds) is not int or not 300 <= seconds <= 3600 or not isinstance(label, str) or not 1 <= len(label) <= 80:
            raise ValueError()
        if values['encryption_key'] in {getattr(settings, name, '') for name in (
                'AUTH_TOTP_ENCRYPTION_KEY', 'ADMINCORE_FIELD_ENCRYPTION_KEY', 'SECRET_KEY')}:
            raise ValueError()
        result = Provider(**values, label=label, session_seconds=seconds)
        result.cipher
        return result
    except (ValueError, TypeError, AttributeError):
        raise SSOUnavailable() from None
