"""Device-bound cache confirmations preserve durable uncertain outcomes."""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session, session_id
from apps.core import cache_management as manager
from apps.core.cache_keys import config_cache_key
from apps.core.cache_views import CacheThrottle
from apps.core.models import SystemConfig
from apps.logs.models import OperationLog

pytestmark = pytest.mark.django_db
ROOT = '/api/v1/system/cache/'
User = get_user_model()


@pytest.fixture(autouse=True)
def throttle():
    CacheThrottle.cache.clear()


@pytest.fixture
def cached():
    row = SystemConfig.objects.create(key='brand.name', value='fixture')
    key = config_cache_key(row.pk, row.version)
    cache.set(key, 'keep')
    return key


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(issue_session(user).access_token))
    return client


def preview(client):
    response = client.post(ROOT + 'preview/', {'namespace': 'configuration'}, format='json')
    assert response.status_code == 200, response.data
    return {'namespace': 'configuration', 'token': response.data['data']['token']}


def clear(client, confirmation):
    return client.post(ROOT + 'clear/', confirmation, format='json')


def test_same_user_other_device_cannot_reuse_confirmation(admin_user, cached):
    first, second = client_for(admin_user), client_for(admin_user)
    confirmation = preview(first)
    payload = signing.loads(confirmation['token'], salt=manager.SALT)
    assert payload['sid']
    assert clear(second, confirmation).status_code == 409
    assert cache.get(cached) == 'keep'
    assert not OperationLog.objects.filter(resource='business_cache').exists()
    assert clear(first, confirmation).status_code == 200
    assert cache.get(cached) is None


@pytest.mark.parametrize('operation', ('preview', 'clear'))
@pytest.mark.parametrize('change,expected', [
    ({'is_staff': False, 'is_superuser': False}, 403),
    ({'is_active': False}, 401),
    ({'must_change_password': True}, 403),
])
def test_stale_entry_actor_cannot_preview_or_clear(admin_user, cached, operation, change, expected):
    client = APIClient()
    client.force_authenticate(admin_user)
    confirmation = preview(client)
    User.objects.filter(pk=admin_user.pk).update(**change)
    response = (client.post(ROOT + 'preview/', {'namespace': 'configuration'}, format='json')
                if operation == 'preview' else clear(client, confirmation))
    assert response.status_code == expected
    assert cache.get(cached) == 'keep'
    assert not OperationLog.objects.filter(resource='business_cache').exists()


@pytest.mark.parametrize('operation', ('preview', 'clear'))
def test_device_revoked_after_request_authentication_cannot_touch_cache(admin_user, cached, operation):
    client = client_for(admin_user)
    confirmation = preview(client)
    original = manager.authorize_write

    def revoke(request, code=None, **kwargs):
        AuthSession.objects.filter(pk=session_id(request.auth)).update(revoked_at=timezone.now())
        return original(request, code, **kwargs)

    with patch.object(manager, 'authorize_write', side_effect=revoke):
        response = (client.post(ROOT + 'preview/', {'namespace': 'configuration'}, format='json')
                    if operation == 'preview' else clear(client, confirmation))
    assert response.status_code == 401
    assert cache.get(cached) == 'keep'
    assert not OperationLog.objects.filter(resource='business_cache').exists()


def test_revocation_between_audit_and_deletion_is_checked_again(admin_user, cached):
    client = client_for(admin_user)
    confirmation = preview(client)
    original = manager.authorize_write
    calls = 0

    def revoke_second(request, code=None, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            AuthSession.objects.filter(pk=session_id(request.auth)).update(revoked_at=timezone.now())
        return original(request, code, **kwargs)

    with patch.object(manager, 'authorize_write', side_effect=revoke_second), patch.object(manager.cache, 'delete_many') as deletion:
        assert clear(client, confirmation).status_code == 401
    assert calls == 2
    deletion.assert_not_called()
    assert cache.get(cached) == 'keep'
    log = OperationLog.objects.get(resource='business_cache')
    assert log.status == 503 and json.loads(log.description)['outcome'] == 'unconfirmed'


@pytest.mark.django_db(transaction=True)
def test_uncertain_audit_commits_before_locked_external_failure(admin_user, cached):
    client = client_for(admin_user)
    confirmation = preview(client)
    original = OperationLog.objects.create

    def durable(**kwargs):
        assert not connection.in_atomic_block
        return original(**kwargs)

    def failure(keys):
        assert connection.in_atomic_block
        assert OperationLog.objects.get(resource='business_cache').status == 503
        raise RuntimeError('fixture external failure')

    with patch.object(OperationLog.objects, 'create', side_effect=durable), patch.object(manager.cache, 'delete_many', side_effect=failure):
        assert clear(client, confirmation).status_code == 503
    assert cache.get(cached) == 'keep'
    assert OperationLog.objects.get(resource='business_cache').status == 503


def test_failed_initial_audit_prevents_external_deletion(admin_user, cached):
    client = client_for(admin_user)
    confirmation = preview(client)
    with patch.object(OperationLog.objects, 'create', side_effect=RuntimeError('fixture audit failure')):
        assert clear(client, confirmation).status_code == 500
    assert cache.get(cached) == 'keep'
    assert not OperationLog.objects.filter(resource='business_cache').exists()


def test_tampered_sid_is_rejected_before_audit(admin_user, cached):
    client = client_for(admin_user)
    confirmation = preview(client)
    payload = signing.loads(confirmation['token'], salt=manager.SALT)
    payload['sid'] = 'other-session'
    confirmation['token'] = signing.dumps(payload, salt=manager.SALT)
    assert clear(client, confirmation).status_code == 409
    assert cache.get(cached) == 'keep'
    assert not OperationLog.objects.filter(resource='business_cache').exists()
