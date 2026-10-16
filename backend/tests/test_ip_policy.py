import ipaddress
from io import StringIO
from unittest.mock import patch
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import PermissionDenied
from apps.core.modules import PRESETS, MODULES
from apps.core.contracts import validate_registry
from apps.ip_policy.models import IPPolicy
from apps.ip_policy.services import enforce, permits
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole

pytestmark = pytest.mark.django_db
URL = '/api/v1/ip-policy/'
PASSWORD = 'Admin#12345'


@pytest.fixture(autouse=True)
def enable(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'ip_policy')
    settings.ROOT_URLCONF = 'tests.ip_policy_urls'
    IPPolicy.objects.get_or_create(pk=1)


def values(**overrides):
    return {'enabled': True, 'allow': ['127.0.0.1'], 'deny': [], 'version': 1, 'current_password': PASSWORD, **overrides}


def test_default_off_and_disabled_module_no_queries(admin_client, settings):
    validate_registry(MODULES)
    assert 'ip_policy' not in PRESETS['standard']
    assert admin_client.get(URL).json()['data']['enabled'] is False
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'ip_policy')
    with CaptureQueriesContext(connection) as queries:
        enforce(RequestFactory().get('/api/v1/auth/login/'))
    assert not queries
    assert admin_client.get(URL).status_code == 404


def test_update_canonicalization_password_audit_and_conflict(admin_client):
    response = admin_client.put(URL, values(allow=['127.0.0.1', '2001:db8::12/64']), format='json')
    assert response.status_code == 200, response.content
    data = response.json()['data']
    assert data['version'] == 2 and data['allow'] == ['127.0.0.1/32', '2001:db8::/64']
    assert 'current_password' not in data
    assert response['Cache-Control'] == 'private, no-store'
    log = OperationLog.objects.get(resource='ip_policy')
    assert log.before_values['enabled'] is False and log.after_values['enabled'] is True
    assert PASSWORD not in str(log.description)
    assert admin_client.put(URL, values(), format='json').status_code == 409
    assert IPPolicy.objects.get().version == 2


@pytest.mark.parametrize('payload', [values(allow=['bad']), values(allow=['::1%eth0']),
    values(allow=['127.0.0.1', '127.0.0.1/32']), values(deny=['10.0.0.1'] * 101),
    values(unknown=True), values(version=0), values(version=1.2), values(current_password='wrong'),
    {'enabled': True, 'version': 1}, values(allow=['192.0.2.0/24']), values(deny=['127.0.0.0/8'])])
def test_invalid_or_lockout_never_writes(admin_client, payload):
    response = admin_client.put(URL, payload, format='json')
    assert response.status_code in (400, 403), response.content
    assert IPPolicy.objects.get().version == 1
    assert not OperationLog.objects.filter(resource='ip_policy').exists()


@pytest.mark.parametrize('source,allow,deny,expected', [
    ('192.0.2.5', ['192.0.2.0/24'], [], True), ('192.0.3.5', ['192.0.2.0/24'], [], False),
    ('192.0.2.5', ['192.0.2.0/24'], ['192.0.2.5/32'], False), ('2001:db8::1', ['2001:db8::/32'], [], True),
    ('2001:db9::1', ['2001:db8::/32'], [], False), ('192.0.2.1', [], ['2001:db8::/32'], True),
    ('::ffff:192.0.2.1', [], ['192.0.2.0/24'], False), ('::ffff:192.0.2.1', ['192.0.2.0/24'], [], True),
    (None, [], [], False), ('bad', [], [], False), ('fe80::1%eth0', [], [], False),
    ('192.0.2.1', ['corrupt'], [], False), ('192.0.2.1', [], ['corrupt'], False)])
def test_ip_network_semantics(source, allow, deny, expected):
    assert permits({'enabled': True, 'allow': allow, 'deny': deny}, source) is expected


def test_all_api_admin_and_legacy_paths_denied_only_exact_probes_exempt(admin_client):
    IPPolicy.objects.filter(pk=1).update(enabled=True, allow=['192.0.2.0/24'])
    for path in [URL, URL + 'preview/', '/api/v1/auth/login/', '/api/v1/auth/refresh/',
                 '/api/v1/auth/password-reset/', '/admin/', '/api/v1/modules/', '/api/v1/health/extra/', '/api/v0/users/']:
        response = admin_client.get(path)
        assert response.status_code == 403, (path, response.content)
        assert response.json()['message'] == '当前来源不允许访问'
    assert admin_client.get('/api/v1/health/live/').status_code == 200
    assert admin_client.get('/api/v1/users/', REMOTE_ADDR='192.0.2.1').status_code == 200


def test_spoofed_forwarding_ignored_and_trusted_chain_applied(admin_client, settings):
    IPPolicy.objects.filter(pk=1).update(enabled=True, allow=['192.0.2.0/24'])
    assert admin_client.get(URL, REMOTE_ADDR='198.51.100.1', HTTP_X_FORWARDED_FOR='192.0.2.1').status_code == 403
    settings.ADMINCORE_TRUSTED_PROXIES = (ipaddress.ip_network('10.0.0.0/8'),)
    assert admin_client.get(URL, REMOTE_ADDR='10.1.1.1', HTTP_X_FORWARDED_FOR='192.0.2.1,10.1.1.2').status_code == 200
    assert admin_client.get(URL, REMOTE_ADDR='10.1.1.1', HTTP_X_FORWARDED_FOR='192.0.2.1,198.51.100.1').status_code == 403
    assert admin_client.get(URL, REMOTE_ADDR='10.1.1.1', HTTP_X_FORWARDED_FOR='invalid').status_code == 403


def test_preview_is_current_source_only_and_does_not_write(admin_client):
    response = admin_client.post(URL + 'preview/', {'enabled': True, 'allow': ['192.0.2.0/24'], 'deny': []}, format='json')
    assert response.json()['data'] == {'source_ip': '127.0.0.1', 'allowed': False}
    assert IPPolicy.objects.get().version == 1
    assert admin_client.post(URL + 'preview/', {'enabled': True, 'allow': [], 'deny': [], 'source_ip': '8.8.8.8'}, format='json').status_code == 400


def test_permission_boundaries_and_immediate_revocation(member_client, member_user):
    assert member_client.get(URL).status_code == 403
    role = Role.objects.create(name='policy-read')
    permission = Permission.objects.create(resource='ip_policy', action='read', name='策略只读', code='ip_policy:read')
    RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=member_user, role=role)
    assert member_client.get(URL).status_code == 200
    assert member_client.put(URL, values(current_password='Member#12345'), format='json').status_code == 403
    role.is_active = False; role.save()
    assert member_client.get(URL).status_code == 403


def test_audit_failure_rolls_back_and_database_failure_closes(admin_client):
    with patch('apps.ip_policy.services.write_audit', side_effect=RuntimeError('audit unavailable')):
        response = admin_client.put(URL, values(), format='json')
    assert response.status_code == 500
    assert IPPolicy.objects.get().version == 1
    with patch('apps.ip_policy.services.current_policy', side_effect=RuntimeError('private-database-secret')):
        response = admin_client.get('/api/v1/users/')
    assert response.status_code == 503
    assert 'secret' not in response.content.decode()
    IPPolicy.objects.all().delete()
    assert admin_client.get('/api/v1/auth/login/').status_code == 503


def test_terminal_recovery_explicit_confirmation_and_audit(admin_client):
    IPPolicy.objects.filter(pk=1).update(enabled=True, deny=['127.0.0.0/8'])
    assert admin_client.get(URL).status_code == 403
    for options in [{'reason': 'recover'}, {'confirm_disable': True, 'reason': ''}]:
        with pytest.raises(CommandError):
            call_command('disable_ip_policy', stdout=StringIO(), **options)
    call_command('disable_ip_policy', confirm_disable=True, reason='operator recovery', stdout=StringIO())
    assert admin_client.get(URL).status_code == 200
    assert IPPolicy.objects.get().version == 2
    assert OperationLog.objects.filter(resource='ip_policy', action='emergency_disable').count() == 1


def test_password_failure_limit_and_cache_unavailable_do_not_write(admin_client):
    for _ in range(5):
        assert admin_client.put(URL, values(current_password='wrong'), format='json').status_code == 403
    assert admin_client.put(URL, values(), format='json').status_code == 429
    assert IPPolicy.objects.get().version == 1
    from django.core.cache import cache
    cache.clear()
    original_get = cache.get
    def fail_confirmation(key, *args, **kwargs):
        if key.startswith('password-confirmation:'):
            raise RuntimeError('private cache')
        return original_get(key, *args, **kwargs)
    with patch('apps.auth_app.reauthentication.cache.get', side_effect=fail_confirmation):
        response = admin_client.put(URL, values(), format='json')
    assert response.status_code == 503 and b'private cache' not in response.content
    assert IPPolicy.objects.get().version == 1


def test_english_denial_and_canonical_ipv4_mapped_rules(admin_client):
    IPPolicy.objects.filter(pk=1).update(enabled=True, deny=['127.0.0.1/32'])
    response = admin_client.get(URL, HTTP_ACCEPT_LANGUAGE='en-US')
    assert response.status_code == 403
    assert response.json()['message'] == 'Access from this source is not allowed'


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_policy_writes_have_one_winner(settings):
    if connection.vendor != 'postgresql':
        pytest.skip('行锁验收只在独立 PostgreSQL 执行')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.contrib.auth import get_user_model
    from django.db import close_old_connections
    from rest_framework.test import APIClient
    from apps.auth_app.sessions import issue_session
    users = [get_user_model().objects.create_superuser(f'policy_writer_{i}', password=PASSWORD) for i in range(2)]
    tokens = [str(issue_session(user).access_token) for user in users]
    barrier = Barrier(2)
    def write(raw):
        close_old_connections()
        try:
            client = APIClient(); client.credentials(HTTP_AUTHORIZATION=f'Bearer {raw}')
            barrier.wait(timeout=10)
            return client.put(URL, values(), format='json').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, tokens))
    assert sorted(outcomes) == [200, 409]
    assert IPPolicy.objects.get().version == 2
    assert OperationLog.objects.filter(resource='ip_policy', action='update').count() == 1


def test_realtime_checks_policy_at_connect_and_each_snapshot(member_user):
    from config.realtime_asgi import _ip_request, _headers, _policy_acquire, _policy_snapshot
    from apps.auth_app.sessions import issue_session
    from django.test import override_settings
    from apps.core.models import RealtimeLease
    raw = str(issue_session(member_user).access_token)
    request = _ip_request({'client': ('192.0.2.1', 1234)}, {'x-forwarded-for': '127.0.0.1'})
    with override_settings(ADMINCORE_MODULES=('realtime', 'ip_policy')):
        IPPolicy.objects.filter(pk=1).update(enabled=True, allow=['192.0.2.0/24'])
        lease = _policy_acquire(raw, request)
        assert _policy_snapshot(raw, lease, request) == {}
        IPPolicy.objects.filter(pk=1).update(deny=['192.0.2.1/32'])
        with pytest.raises(PermissionDenied):
            _policy_snapshot(raw, lease, request)
        with pytest.raises(PermissionDenied):
            _policy_acquire(raw, request)
        assert RealtimeLease.objects.count() == 1
    with pytest.raises(ValueError):
        _headers({'headers': [(b'x-forwarded-for', b'1.1.1.1'), (b'x-forwarded-for', b'2.2.2.2')]})
