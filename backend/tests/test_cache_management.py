import json
from unittest.mock import patch

import pytest
from django.core import signing
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.core import cache_management as manager
from apps.core.cache_views import CacheThrottle
from apps.core.cache_keys import config_cache_key, dictionary_cache_key
from apps.core.models import SystemConfig, DataDictionary
from apps.core.system_config import config_value
from apps.logs.models import OperationLog

pytestmark = pytest.mark.django_db
ROOT = '/api/v1/system/cache/'


@pytest.fixture(autouse=True)
def counters():
    CacheThrottle.cache.clear()


@pytest.fixture
def rows():
    config = SystemConfig.objects.create(key='brand.name', value='Business name')
    dictionary = DataDictionary.objects.create(code='cache_fixture', name='Fixture', items=[])
    return config, dictionary


def preview(admin_client, namespace='configuration'):
    response = admin_client.post(ROOT + 'preview/', {'namespace': namespace}, format='json')
    assert response.status_code == 200, response.data
    return response.json()['data']


def execute(client, data):
    return client.post(ROOT + 'clear/', {'namespace': data['namespace'], 'token': data['token']}, format='json')


def test_catalog_no_values_or_raw_keys_and_rebuild(admin_client, rows):
    config, dictionary = rows
    assert config_value('brand.name') == 'Business name'
    config_key = config_cache_key(config.pk, config.version)
    dictionary_key = dictionary_cache_key(dictionary.pk, dictionary.version)
    cache.set(dictionary_key, ['business-dictionary-secret'])
    # Protected markers share the same backend: cleanup must never flush it.
    markers = ['throttle_user_fixture', 'login_attempt_fixture', 'session_fixture',
               'celery_fixture', 'lock_fixture', 'admincore:config:unregistered:v1',
               config_cache_key(config.pk, config.version - 1)]
    for key in markers:
        cache.set(key, 'protected', timeout=300)
    catalog = admin_client.get(ROOT)
    assert catalog.status_code == 200 and catalog['Cache-Control'] == 'private, no-store'
    assert catalog.json()['data']['backend'] == 'in_process'
    assert 'Business name' not in str(catalog.data) and str(config.pk) not in str(catalog.data)
    data = preview(admin_client)
    assert data['candidate_count'] == 1
    response = execute(admin_client, data)
    assert response.status_code == 200 and response.json()['data']['candidate_count'] == 1
    assert cache.get(config_key) is None
    assert cache.get(dictionary_key) == ['business-dictionary-secret']
    assert all(cache.get(key) == 'protected' for key in markers)
    assert config_value('brand.name') == 'Business name'
    assert cache.get(config_key) == 'Business name'
    config.refresh_from_db()
    assert config.version == 1 and config.value == 'Business name'
    log = OperationLog.objects.get(resource='business_cache')
    assert log.status == 200 and json.loads(log.description)['outcome'] == 'completed'
    assert data['token'] not in log.description and 'Business name' not in log.description


def test_dictionary_isolation_and_disabled_rows(admin_client, rows):
    config, dictionary = rows
    dictionary.is_active = False
    dictionary.save()
    a, b = config_cache_key(config.pk, 1), dictionary_cache_key(dictionary.pk, 1)
    cache.set(a, 'protected')
    cache.set(b, 'cached')
    assert execute(admin_client, preview(admin_client, 'dictionaries')).status_code == 200
    assert cache.get(b) is None and cache.get(a) == 'protected'


def test_unknown_scope_and_unexpected_fields_never_touch_cache(admin_client):
    with patch.object(manager.cache, 'delete_many') as deletion:
        for payload in [{'namespace': '*'}, {'namespace': 'configuration', 'prefix': '*'},
                        {'namespace': 'configuration', 'key': 'throttle'}, {'namespace': 'sessions'}]:
            assert admin_client.post(ROOT + 'preview/', payload, format='json').status_code == 400
        data = preview(admin_client)
        assert admin_client.post(ROOT + 'clear/', {**data, 'all': True}, format='json').status_code == 400
        assert admin_client.get(ROOT + 'clear/').status_code == 405
        deletion.assert_not_called()


def test_empty_and_repeated_cleanup_does_not_claim_deleted_count(admin_client):
    data = preview(admin_client)
    with patch.object(manager.cache, 'delete_many') as deletion:
        for _ in range(2):
            response = execute(admin_client, data)
            assert response.status_code == 200 and response.data['data']['candidate_count'] == 0
            assert 'deleted_count' not in response.data['data']
        deletion.assert_not_called()


@pytest.mark.parametrize('case', ['tampered', 'expired', 'user', 'session', 'namespace', 'backend'])
def test_invalid_confirmations_rejected(admin_client, admin_user, rows, case):
    data = preview(admin_client)
    payload = signing.loads(data['token'], salt=manager.SALT)
    if case == 'tampered':
        data['token'] += 'x'
    elif case == 'expired':
        with patch('django.core.signing.time.time', return_value=0):
            data['token'] = signing.dumps(payload, salt=manager.SALT)
    else:
        payload[case] = {'user': 'someone-else', 'session': 99, 'namespace': 'dictionaries', 'backend': 'shared'}[case]
        data['token'] = signing.dumps(payload, salt=manager.SALT)
    with patch.object(manager.cache, 'delete_many') as deletion:
        assert execute(admin_client, data).status_code == 409
        deletion.assert_not_called()
    assert not OperationLog.objects.filter(resource='business_cache').exists()


def test_data_changed_since_preview_conflicts(admin_client, rows):
    data = preview(admin_client)
    SystemConfig.objects.filter(pk=rows[0].pk).update(version=2)
    assert execute(admin_client, data).status_code == 409
    assert execute(admin_client, preview(admin_client)).status_code == 200


def test_bound_is_explicit_and_excess_refused(admin_client):
    DataDictionary.objects.bulk_create([DataDictionary(code=f'd{i}', name='Fixture') for i in range(manager.LIMIT + 1)])
    catalog = admin_client.get(ROOT).json()['data']['namespaces'][1]
    assert catalog['over_limit'] and catalog['candidate_count'] == manager.LIMIT
    with patch.object(manager.cache, 'delete_many') as deletion:
        assert admin_client.post(ROOT + 'preview/', {'namespace': 'dictionaries'}, format='json').status_code == 400
        deletion.assert_not_called()


def test_cache_failure_keeps_uncertain_audit_without_leaking_detail(admin_client, rows):
    data = preview(admin_client)
    with patch.object(manager.cache, 'delete_many', side_effect=RuntimeError('redis://credential-secret/private')):
        response = execute(admin_client, data)
    assert response.status_code == 503 and 'credential-secret' not in str(response.data)
    log = OperationLog.objects.get(resource='business_cache')
    assert log.status == 503 and json.loads(log.description)['outcome'] == 'unconfirmed'


def test_suppressed_redis_errors_do_not_report_success(admin_client, rows):
    with patch.object(manager, 'backend_mode', return_value='shared'):
        data = preview(admin_client)
        with patch.object(manager.cache, 'delete_many', return_value=None):
            assert execute(admin_client, data).status_code == 503
    assert OperationLog.objects.get(resource='business_cache').status == 503


def test_audit_failure_prevents_cleanup_and_final_audit_failure_is_uncertain(admin_client, rows):
    data = preview(admin_client)
    with patch.object(OperationLog.objects, 'create', side_effect=RuntimeError('audit unavailable')), patch.object(manager.cache, 'delete_many') as deletion:
        assert execute(admin_client, data).status_code == 500
        deletion.assert_not_called()
    # Patch only updates; initial insertion must be durable before touching cache.
    original = OperationLog.save
    def fail_update(instance, *args, **kwargs):
        if kwargs.get('update_fields'):
            raise RuntimeError('audit unavailable')
        return original(instance, *args, **kwargs)
    with patch.object(OperationLog, 'save', fail_update):
        assert execute(admin_client, data).status_code == 503
    assert OperationLog.objects.get(resource='business_cache').status == 503


def test_member_anonymous_module_shutdown_and_force_password_rejected(admin_client, member_client, member_user, settings, client):
    for endpoint in [ROOT, ROOT + 'preview/', ROOT + 'clear/']:
        method = 'get' if endpoint == ROOT else 'post'
        assert getattr(client, method)(endpoint).status_code == 401
        assert getattr(member_client, method)(endpoint).status_code == 403
    from apps.permissions.models import Permission, Role, RolePermission, UserRole
    role = Role.objects.create(name='cache-fixture')
    perm = Permission.objects.create(resource='fixture', action='all', code='*', name='fixture')
    RolePermission.objects.create(role=role, permission=perm)
    UserRole.objects.create(role=role, user=member_user)
    assert member_client.get(ROOT).status_code == 403
    settings.ADMINCORE_MODULES = []
    assert admin_client.get(ROOT).status_code == 404
    settings.ADMINCORE_MODULES = ['system']
    assert admin_client.get(ROOT).status_code == 200


def test_permission_scope_rechecked_and_unsupported_backend(admin_client, rows, settings):
    data = preview(admin_client)
    with patch.object(manager, 'has_permission_code', return_value=False):
        assert execute(admin_client, data).status_code == 403
    settings.CACHES = {'default': {'BACKEND': 'unsupported.Cache'}}
    assert admin_client.post(ROOT + 'preview/', {'namespace': 'configuration'}, format='json').status_code == 503


def test_current_session_change_invalidates_previous_preview(admin_client, admin_user):
    data = preview(admin_client)
    admin_user.session_version += 1
    admin_user.save(update_fields=['session_version'])
    # A newly authenticated request may not reuse the previous session's confirmation.
    current = APIClient()
    current.force_authenticate(admin_user)
    assert execute(current, data).status_code == 409


def test_management_rate_limit_independent_of_business_cache(admin_client):
    for _ in range(20):
        assert admin_client.get(ROOT).status_code == 200
    assert admin_client.get(ROOT).status_code == 429


def test_bootstrap_does_not_expand_existing_roles_or_restore_deleted_menu(admin_user, monkeypatch):
    from django.core.management import call_command
    from io import StringIO
    from apps.permissions.models import Role, RolePermission, Menu
    admin_user.set_password('Existing-cache-fixture#2026')
    admin_user.save()
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'unused-existing-user')
    role = Role.objects.create(name='系统管理员')
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not RolePermission.objects.filter(role=role, permission__code__in=['cache:read', 'cache:clear']).exists()
    Menu.objects.filter(path='/system/cache').delete()
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not Menu.objects.filter(path='/system/cache').exists()


def test_force_password_restriction_applies_before_cache_access(admin_client, admin_user):
    admin_user.must_change_password = True
    admin_user.save(update_fields=['must_change_password'])
    assert admin_client.get(ROOT).status_code == 403
    assert admin_client.post(ROOT + 'preview/', {'namespace': 'configuration'}, format='json').status_code == 403
