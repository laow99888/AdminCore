"""显式登记版本生命周期；仅通知，不自动撤路由、不重写业务响应。"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
import re
from urllib.parse import urlsplit

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from django.views.decorators.http import require_safe

VERSIONS = ('v1',)
MIN_COMPATIBILITY_DAYS = 90
DOCUMENTATION = '/api/versions/'
VERSION_PATH = re.compile(r'^/api/(v[1-9][0-9]*)/')


@dataclass(frozen=True)
class Policy:
    version: str
    deprecated_at: datetime | None = None
    sunset_at: datetime | None = None
    migration_url: str | None = None

    def describe(self, now):
        status = 'active'
        if self.deprecated_at:
            status = 'scheduled' if now < self.deprecated_at else 'deprecated'
        if self.sunset_at and now >= self.sunset_at:
            status = 'sunset_due'
        return {'version': self.version, 'status': status,
                'deprecated_at': self.deprecated_at.isoformat() if self.deprecated_at else None,
                'sunset_at': self.sunset_at.isoformat() if self.sunset_at else None,
                'migration_url': self.migration_url}

    def headers(self):
        result = {'X-API-Version': self.version}
        if self.deprecated_at:
            result['Deprecation'] = '@' + str(int(self.deprecated_at.timestamp()))
            result['Link'] = f'<{self.migration_url}>; rel="deprecation"'
        if self.sunset_at:
            result['Sunset'] = format_datetime(self.sunset_at, usegmt=True)
        return result


def _invalid():
    # 不把原始环境值或URL输出到日志（可能误填凭据）。
    raise ImproperlyConfigured('ADMINCORE_API_LIFECYCLE 无效，参见 docs/API版本与废弃流程-2026-10-15.md') from None


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value):
        _invalid()
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        _invalid()
    if result.year < 1970:
        _invalid()
    return result


def _migration_url(value):
    if not isinstance(value, str) or len(value) > 500 or not value.isascii() or any(char in value for char in '<>"\\') or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        _invalid()
    if value == DOCUMENTATION:
        return value
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.port not in (None, 443):
            _invalid()
    except ValueError:
        _invalid()
    return value


def parse_policies(raw):
    if not isinstance(raw, dict) or set(raw) - set(VERSIONS):
        _invalid()
    result = {}
    for version in VERSIONS:
        values = raw.get(version, {})
        if not isinstance(values, dict) or set(values) - {'deprecated_at', 'sunset_at', 'migration_url'}:
            _invalid()
        if not values:
            result[version] = Policy(version)
            continue
        if 'deprecated_at' not in values or 'migration_url' not in values:
            _invalid()
        deprecated = _date(values['deprecated_at'])
        sunset = _date(values['sunset_at']) if 'sunset_at' in values else None
        if sunset and sunset - deprecated < timedelta(days=MIN_COMPATIBILITY_DAYS):
            _invalid()
        result[version] = Policy(version, deprecated, sunset, _migration_url(values['migration_url']))
    return result


def load_configuration(raw):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _invalid()
            result[key] = value
        return result
    if len(raw) > 4000:
        _invalid()
    try:
        values = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, TypeError):
        _invalid()
    parse_policies(values)
    return values


def response_headers(path, policies=None):
    match = VERSION_PATH.match(path)
    policies = policies if policies is not None else parse_policies(settings.ADMINCORE_API_LIFECYCLE)
    policy = policies.get(match[1]) if match else None
    return policy.headers() if policy else {}


class APILifecycleMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.policies = parse_policies(settings.ADMINCORE_API_LIFECYCLE)
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def decorate(self, request, response):
        for name, value in response_headers(request.path_info, self.policies).items():
            if name == 'Link' and response.has_header('Link'):
                value = response['Link'] + ', ' + value
            response[name] = value
        return response

    def __call__(self, request):
        if self.is_async:
            return self.async_call(request)
        return self.decorate(request, self.get_response(request))

    async def async_call(self, request):
        return self.decorate(request, await self.get_response(request))


@require_safe
def api_versions(request):
    now = datetime.now(timezone.utc)
    response = JsonResponse({'versions': [policy.describe(now) for policy in parse_policies(settings.ADMINCORE_API_LIFECYCLE).values()],
                             'minimum_compatibility_days': MIN_COMPATIBILITY_DAYS,
                             'automatic_retirement': False,
                             'policy': 'Deprecation announces a migration period; Sunset is advisory. Removal requires a separate reviewed release. No replacement version is implied.'})
    response['Cache-Control'] = 'no-store'
    return response


def schema_lifecycle(result, generator, request, public):
    policies = parse_policies(settings.ADMINCORE_API_LIFECYCLE)
    now = datetime.now(timezone.utc)
    result['info']['x-api-lifecycle'] = [policy.describe(now) for policy in policies.values()]
    for path, item in result.get('paths', {}).items():
        match = VERSION_PATH.match(path)
        policy = policies.get(match[1]) if match else None
        if not policy:
            continue
        for method, operation in item.items():
            if method not in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}:
                continue
            operation['x-api-lifecycle'] = policy.describe(now)
            if policy.deprecated_at and now >= policy.deprecated_at:
                operation['deprecated'] = True
            for response in operation.get('responses', {}).values():
                if '$ref' in response:
                    continue
                headers = response.setdefault('headers', {})
                for name, value in policy.headers().items():
                    headers[name] = {'description': 'API lifecycle; see /api/versions/. Does not change authentication, caching or response body.',
                                     'schema': {'type': 'string'}, 'example': value}
    return result
