from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.api_credentials.authentication import digest
from apps.api_credentials.models import APICredential
from apps.core.models import DataScopeGrant
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.tasks.models import TaskRecord

pytestmark = pytest.mark.django_db
BASE = '/api/v1/api-credentials/'
PASSWORD = 'Fixture-only#2026'


@pytest.fixture(autouse=True)
def enable_api_credentials(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'api_credentials', 'example')
    settings.ROOT_URLCONF = 'tests.api_credential_urls'


@pytest.fixture
def owner():
    user = get_user_model().objects.create_user('integration-owner', password=PASSWORD)
    role = Role.objects.create(name='Integration role')
    UserRole.objects.create(user=user, role=role)
    for code in ('api_credential:read', 'api_credential:create', 'api_credential:revoke', 'task:read', 'example:read'):
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': code, 'resource': resource, 'action': action})
        RolePermission.objects.create(role=role, permission=permission)
    DataScopeGrant.objects.create(role=role, resource='task', scope='self')
    return user


@pytest.fixture
def session_client(owner):
    client = APIClient()
    response = client.post('/api/v1/auth/login/', {'username': owner.username, 'password': PASSWORD}, format='json')
    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.json()["access"]}')
    return client


def issue(client, **overrides):
    body = {'name': 'integration fixture', 'scopes': ['task:read'],
            'expires_at': (timezone.now() + timedelta(days=1)).isoformat(), 'current_password': PASSWORD}
    return client.post(BASE + 'credentials/', {**body, **overrides}, format='json')


def token_client(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='ApiToken ' + token)
    return client


def issued(session_client):
    response = issue(session_client)
    assert response.status_code == 201, response.data
    data = response.json()['data']
    return data, token_client(data['token'])


def test_secret_once_hash_only_owner_list_and_safe_audit(session_client, owner):
    data, client = issued(session_client)
    row = APICredential.objects.get(pk=data['id'])
    secret = data['token'].split('.')[1]
    assert row.secret_digest == digest(secret)
    assert data['token'] not in repr(row.__dict__) and secret not in repr(row.__dict__)
    response = session_client.get(BASE + 'credentials/')
    assert response.status_code == 200
    assert 'token' not in response.json()['data']['items'][0]
    assert 'secret_digest' not in response.content.decode()
    for _ in range(3):
        assert client.get(BASE + 'tasks/').status_code == 200
    row.refresh_from_db()
    assert row.last_used_at and row.usage_count == 3
    logs = OperationLog.objects.filter(resource='api_credential')
    assert logs.count() == 2  # creation and first activation, not one per request
    assert secret not in str(list(logs.values())) and PASSWORD not in str(list(logs.values()))


def test_read_only_scope_and_realtime_data_range(session_client, owner):
    own = TaskRecord.objects.create(name='own', creator=owner)
    other = TaskRecord.objects.create(name='other', creator=get_user_model().objects.create_user('other'))
    _, client = issued(session_client)
    response = client.get(BASE + 'tasks/?ordering=-created_at&page_size=1')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['data']['items']] == [str(own.pk)]
    assert set(response.json()['data']['items'][0]) == {'id', 'name', 'task_type', 'status', 'progress', 'created_at', 'started_at', 'completed_at'}
    assert client.get(BASE + f'tasks/{other.pk}/').status_code == 404
    assert client.get(BASE + 'work-items/').status_code == 403
    grant = DataScopeGrant.objects.get(resource='task')
    grant.scope = 'all'; grant.save(update_fields=['scope'])
    assert client.get(BASE + 'tasks/').json()['data']['pagination']['total'] == 2
    RolePermission.objects.filter(permission__code='task:read').delete()
    assert client.get(BASE + 'tasks/').status_code == 403


@pytest.mark.parametrize('path,method', [('credentials/', 'get'), ('credentials/', 'post'), ('tasks/', 'post'),
                                       ('tasks/00000000-0000-0000-0000-000000000000/cancel/', 'post')])
def test_api_secret_cannot_manage_or_write(session_client, path, method):
    _, client = issued(session_client)
    assert getattr(client, method)(BASE + path, {}, format='json').status_code in {401, 403, 404, 405}


def test_api_secret_cannot_authenticate_regular_or_account_routes(session_client):
    _, client = issued(session_client)
    assert client.get('/api/v1/tasks/').status_code == 401
    assert client.get('/api/v1/auth/me/').status_code == 401
    assert client.post('/api/v1/auth/refresh/', {'refresh': client._credentials['HTTP_AUTHORIZATION']}, format='json').status_code in {400, 401}
    assert session_client.get(BASE + 'tasks/').status_code == 401


def test_disabled_then_reenabled_owner_never_revives_old_api_secret(session_client, owner):
    _, client = issued(session_client)
    assert client.get(BASE + 'tasks/').status_code == 200
    owner.is_active = False
    owner.save(update_fields=['is_active'])
    assert client.get(BASE + 'tasks/').status_code == 401
    owner.is_active = True
    owner.save(update_fields=['is_active'])
    assert client.get(BASE + 'tasks/').status_code == 401


@pytest.mark.parametrize('change', ['expire', 'revoke', 'inactive', 'password', 'version', 'force_password', 'inactive_role'])
def test_owner_security_changes_invalidate_credentials(session_client, owner, change):
    data, client = issued(session_client)
    if change == 'expire': APICredential.objects.filter(pk=data['id']).update(expires_at=timezone.now() - timedelta(seconds=1))
    elif change == 'revoke': APICredential.objects.filter(pk=data['id']).update(revoked_at=timezone.now())
    elif change == 'inactive': get_user_model().objects.filter(pk=owner.pk).update(is_active=False)
    elif change == 'password':
        owner.set_password('Different-fixture#2026'); owner.save(update_fields=['password'])
    elif change == 'version': get_user_model().objects.filter(pk=owner.pk).update(session_version=1)
    elif change == 'force_password': get_user_model().objects.filter(pk=owner.pk).update(must_change_password=True)
    else: Role.objects.update(is_active=False)
    assert client.get(BASE + 'tasks/').status_code == (403 if change == 'inactive_role' else 401)


def test_revocation_is_owner_only_and_idempotent(session_client, owner):
    data, client = issued(session_client)
    other = get_user_model().objects.create_user('separate', password=PASSWORD)
    row = APICredential.objects.get(pk=data['id'])
    row.owner = other; row.save(update_fields=['owner'])
    assert session_client.get(BASE + 'credentials/').json()['data']['pagination']['total'] == 0
    assert session_client.post(BASE + f'credentials/{row.pk}/revoke/', {'current_password': PASSWORD}, format='json').status_code == 404
    row.owner = owner; row.save(update_fields=['owner'])
    path = BASE + f'credentials/{row.pk}/revoke/'
    assert session_client.post(path, {'current_password': PASSWORD}, format='json').status_code == 200
    count = OperationLog.objects.filter(resource='api_credential').count()
    assert session_client.post(path, {'current_password': PASSWORD}, format='json').status_code == 200
    assert OperationLog.objects.filter(resource='api_credential').count() == count
    assert client.get(BASE + 'tasks/').status_code == 401


@pytest.mark.parametrize('overrides', [{'current_password': ''}, {'current_password': 'wrong'}, {'scopes': ['*']},
    {'scopes': ['task:read', 'task:read']}, {'scopes': ['user:sensitive-read']}, {'owner': 'another'},
    {'expires_at': '2000-01-01T00:00:00Z'}, {'expires_at': '2099-01-01T00:00:00Z'}, {'name': ' '}])
def test_issuance_validation_and_confirmation(session_client, overrides):
    response = issue(session_client, **overrides)
    assert response.status_code in {400, 403}
    assert not APICredential.objects.exists()


def test_no_escalation_and_active_limit(session_client):
    RolePermission.objects.filter(permission__code='example:read').delete()
    assert issue(session_client, scopes=['example:read']).status_code == 403
    scopes = session_client.get(BASE + 'credentials/scopes/').json()['data']
    assert [row['code'] for row in scopes] == ['task:read']
    for index in range(20):
        assert issue(session_client, name=str(index)).status_code == 201
    assert issue(session_client).status_code == 400


def test_revoked_device_cannot_issue_or_revoke(session_client, owner):
    get_user_model().objects.filter(pk=owner.pk).update(session_version=owner.session_version + 1)
    assert issue(session_client).status_code == 401


def test_request_limits_and_fail_closed_cache(session_client):
    _, client = issued(session_client)
    # 固定同一分钟；全量覆盖率运行可能恰好跨真实分钟边界。
    now = timezone.now()
    with patch('apps.api_credentials.authentication.REQUESTS_PER_MINUTE', 2), \
            patch('apps.api_credentials.authentication.timezone.now', return_value=now):
        assert client.get(BASE + 'tasks/').status_code == 200
        assert client.get(BASE + 'tasks/').status_code == 200
        response = client.get(BASE + 'tasks/')
        assert response.status_code == 429 and 'Retry-After' in response
        with patch('apps.api_credentials.authentication.timezone.now', return_value=now + timedelta(minutes=1)):
            assert client.get(BASE + 'tasks/').status_code == 200
    with patch('apps.api_credentials.authentication.cache.add', side_effect=RuntimeError('cache unavailable')):
        assert client.get(BASE + 'tasks/').status_code == 503


@pytest.mark.parametrize('query', ['unexpected=x', 'search=a&search=b', 'ordering=password', 'search=' + 'x' * 201])
def test_gateway_uses_query_contract(session_client, query):
    _, client = issued(session_client)
    assert client.get(BASE + 'tasks/?' + query).status_code == 400


def test_disabled_module_and_target_module_fail_closed(session_client, settings):
    _, client = issued(session_client)
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'tasks')
    assert client.get(BASE + 'tasks/').status_code == 403
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'api_credentials')
    assert client.get(BASE + 'tasks/').status_code == 404
    assert session_client.get(BASE + 'credentials/').status_code == 404


@pytest.mark.parametrize('header', ['Bearer x', 'ApiToken invalid', 'ApiToken ac_' + '0' * 32 + '.' + 'a' * 43])
def test_malformed_and_unknown_secret(header):
    client = APIClient(); client.credentials(HTTP_AUTHORIZATION=header)
    assert client.get(BASE + 'tasks/').status_code == 401


def test_wrong_secret_cannot_touch_usage_or_audit(session_client):
    data, _ = issued(session_client)
    wrong = data['token'].split('.')[0] + '.' + 'a' * 43
    assert token_client(wrong).get(BASE + 'tasks/').status_code == 401
    row = APICredential.objects.get(pk=data['id'])
    assert row.last_used_at is None and row.usage_count == 0
    assert OperationLog.objects.filter(resource='api_credential').count() == 1


def test_work_item_scope_uses_safe_summary_and_self_fallback(session_client, owner):
    from apps.example.models import WorkItem
    own = WorkItem.objects.create(title='Own', notes='private-notes', creator=owner)
    other = WorkItem.objects.create(title='Other', creator=get_user_model().objects.create_user('other-work-owner'))
    response = issue(session_client, scopes=['example:read'])
    assert response.status_code == 201
    client = token_client(response.json()['data']['token'])
    response = client.get(BASE + 'work-items/?ordering=priority')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['data']['items']] == [str(own.pk)]
    assert 'notes' not in response.json()['data']['items'][0]
    assert client.get(BASE + f'work-items/{other.pk}/').status_code == 404
    assert client.get(BASE + f'work-items/{own.pk}/').status_code == 200


def test_issuance_rolls_back_if_security_audit_fails(session_client):
    session_client.raise_request_exception = False
    with patch('apps.api_credentials.views.write_audit', side_effect=RuntimeError('fixture audit unavailable')):
        assert issue(session_client).status_code == 500
    assert not APICredential.objects.exists()


def test_ip_attempt_limit_counts_unknown_secrets():
    from apps.api_credentials.authentication import digest
    from django.core.cache import cache
    import time
    key = f'api-credential-attempt:{digest("127.0.0.1")}:{int(time.time() // 60)}'
    cache.set(key, 180, 120)
    response = token_client('invalid').get(BASE + 'tasks/')
    assert response.status_code == 429


def test_stable_gateway_pagination_for_equal_sort_values(session_client, owner):
    from uuid import UUID
    ids = [UUID(int=number) for number in (39, 12, 25)]
    TaskRecord.objects.bulk_create([TaskRecord(id=identifier, creator=owner, name='same') for identifier in ids])
    TaskRecord.objects.filter(pk__in=ids).update(created_at=timezone.now())
    _, client = issued(session_client)
    actual = []
    for page in (1, 2, 3):
        response = client.get(BASE + f'tasks/?page={page}&page_size=1&ordering=-created_at')
        assert response.status_code == 200
        actual.extend(row['id'] for row in response.json()['data']['items'])
    assert actual == [str(identifier) for identifier in sorted(ids)]


def test_schema_dedicated_security_and_no_write_gateways():
    from drf_spectacular.generators import SchemaGenerator
    from drf_spectacular.validation import validate_schema
    from tests.api_credential_urls import urlpatterns
    schema = SchemaGenerator(patterns=urlpatterns).get_schema(public=True)
    validate_schema(schema)
    tasks = schema['paths'][BASE + 'tasks/']
    assert set(tasks) == {'get'}
    assert tasks['get']['security'] == [{'apiCredential': []}]
    assert {'200', '400', '503'} <= set(tasks['get']['responses'])
    assert schema['paths'][BASE + 'credentials/']['post']['security'] == [{'jwtAuth': []}]


def test_rotation_replaces_secret_without_changing_capabilities_or_expiry(session_client, owner):
    data, old = issued(session_client)
    assert old.get(BASE + 'tasks/').status_code == 200
    response = session_client.post(BASE + f'credentials/{data["id"]}/rotate/',
        {'version': data['version'], 'current_password': PASSWORD}, format='json')
    assert response.status_code == 200, response.data
    replacement = response.json()['data']
    assert replacement['version'] == 2 and replacement['rotated_at']
    assert replacement['expires_at'] == data['expires_at'] and replacement['scopes'] == data['scopes']
    assert replacement['accepted_requests'] == 1 and replacement['token'] != data['token']
    assert old.get(BASE + 'tasks/').status_code == 401
    assert token_client(replacement['token']).get(BASE + 'tasks/').status_code == 200
    row = APICredential.objects.get(pk=data['id'])
    assert row.secret_digest == digest(replacement['token'].split('.')[1])
    assert replacement['token'] not in str(list(OperationLog.objects.filter(resource='api_credential').values()))
    stale = session_client.post(BASE + f'credentials/{data["id"]}/rotate/',
        {'version': 1, 'current_password': PASSWORD}, format='json')
    assert stale.status_code == 409
    assert token_client(replacement['token']).get(BASE + 'tasks/').status_code == 200


@pytest.mark.parametrize('change,expected', [('password', 403), ('expired', 400), ('revoked', 400),
    ('permission', 403), ('scope', 403), ('extra', 400), ('boolean', 400), ('wrong-version', 409)])
def test_rotation_fails_closed_without_mutating_secret(session_client, change, expected):
    data, _ = issued(session_client)
    row = APICredential.objects.get(pk=data['id'])
    original = row.secret_digest
    payload = {'version': 1, 'current_password': PASSWORD}
    if change == 'password': payload['current_password'] = 'wrong'
    elif change == 'expired': APICredential.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    elif change == 'revoked': APICredential.objects.filter(pk=row.pk).update(revoked_at=timezone.now())
    elif change == 'permission': RolePermission.objects.filter(permission__code='api_credential:revoke').delete()
    elif change == 'scope': RolePermission.objects.filter(permission__code='task:read').delete()
    elif change == 'extra': payload['scopes'] = ['example:read']
    elif change == 'boolean': payload['version'] = True
    else: payload['version'] = 2
    assert session_client.post(BASE + f'credentials/{row.pk}/rotate/', payload, format='json').status_code == expected
    row.refresh_from_db()
    assert row.secret_digest == original and row.version == 1 and row.rotated_at is None


def test_rotation_audit_failure_rolls_back_secret(session_client):
    data, old = issued(session_client)
    session_client.raise_request_exception = False
    with patch('apps.api_credentials.views.write_audit', side_effect=RuntimeError('audit unavailable')):
        assert session_client.post(BASE + f'credentials/{data["id"]}/rotate/',
            {'version': 1, 'current_password': PASSWORD}, format='json').status_code == 500
    assert old.get(BASE + 'tasks/').status_code == 200
    assert APICredential.objects.get(pk=data['id']).version == 1


def test_usage_counts_authenticated_requests_even_when_business_query_is_invalid(session_client):
    data, client = issued(session_client)
    path = BASE + f'credentials/{data["id"]}/statistics/'
    empty = session_client.get(path).json()['data']
    assert empty['daily'] == [] and empty['accepted_requests'] == 0 and empty['timezone'] == 'UTC'
    assert client.get(BASE + 'tasks/').status_code == 200
    assert client.get(BASE + 'tasks/?unexpected=x').status_code == 400
    assert client.get(BASE + 'work-items/').status_code == 403
    assert token_client(data['token'][:-1] + ('a' if data['token'][-1] != 'a' else 'b')).get(BASE + 'tasks/').status_code == 401
    with patch('apps.api_credentials.authentication.REQUESTS_PER_MINUTE', 2):
        assert client.get(BASE + 'tasks/').status_code == 429
    response = session_client.get(path)
    assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
    stats = response.json()['data']
    assert stats['accepted_requests'] == stats['recent_requests'] == 2
    assert stats['daily'] == [{'day': timezone.now().date().isoformat(), 'requests': 2}]
    assert 'token' not in str(stats) and 'secret_digest' not in str(stats)


@pytest.mark.parametrize('query', ['days=0', 'days=91', 'days=-1', 'days=1.5', 'days=1&days=2',
    'days=一', 'days=' + '9' * 5000, 'owner=anything'])
def test_usage_query_is_strict_and_bounded(session_client, query):
    data, _ = issued(session_client)
    assert session_client.get(BASE + f'credentials/{data["id"]}/statistics/?{query}').status_code == 400


def test_usage_and_rotation_cannot_access_another_owners_credentials(session_client):
    data, _ = issued(session_client)
    APICredential.objects.filter(pk=data['id']).update(owner=get_user_model().objects.create_user('another-owner'))
    assert session_client.get(BASE + f'credentials/{data["id"]}/statistics/').status_code == 404
    assert session_client.post(BASE + f'credentials/{data["id"]}/rotate/',
        {'version': 1, 'current_password': PASSWORD}, format='json').status_code == 404


def test_usage_rolling_retention_does_not_reset_total(session_client):
    from apps.api_credentials.models import CredentialUsageDay
    data, client = issued(session_client)
    day = timezone.now().date()
    CredentialUsageDay.objects.create(credential_id=data['id'], day=day - timedelta(days=90), requests=10)
    CredentialUsageDay.objects.create(credential_id=data['id'], day=day - timedelta(days=89), requests=3)
    APICredential.objects.filter(pk=data['id']).update(accepted_requests=13)
    assert client.get(BASE + 'tasks/').status_code == 200
    # 清理移入已有定时维护任务，认证热路径只计数。
    assert CredentialUsageDay.objects.filter(day=day - timedelta(days=90)).exists()
    from apps.core.tasks import cleanup_expired_sessions
    cleanup_expired_sessions()
    assert not CredentialUsageDay.objects.filter(day=day - timedelta(days=90)).exists()
    stats = session_client.get(BASE + f'credentials/{data["id"]}/statistics/?days=90').json()['data']
    assert stats['accepted_requests'] == 14 and stats['recent_requests'] == 4


def test_gateway_activates_current_tenant_and_rechecks_membership(session_client, owner, settings):
    from apps.core.models import Tenant, TenantMembership
    from apps.core.tenancy import tenant_context
    data, client = issued(session_client)
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(name='凭证甲', slug='credential-a')
    second = Tenant.objects.create(name='凭证乙', slug='credential-b')
    membership = TenantMembership.objects.create(user=owner, tenant=first)
    with tenant_context(first.pk):
        own = TaskRecord.objects.create(name='tenant-a-task', creator=owner)
    with tenant_context(second.pk):
        other = TaskRecord.objects.create(name='tenant-b-task', creator=owner)
    response = client.get(BASE + 'tasks/')
    assert response.status_code == 200, response.content
    assert [row['id'] for row in response.json()['data']['items']] == [str(own.pk)]
    assert client.get(BASE + 'tasks/', HTTP_X_ADMINCORE_TENANT=str(second.pk)).status_code == 403
    assert client.get(BASE + f'tasks/{other.pk}/', HTTP_X_ADMINCORE_TENANT=str(first.pk)).status_code == 404
    TenantMembership.objects.create(user=owner, tenant=second)
    assert client.get(BASE + 'tasks/').status_code == 400
    assert client.get(BASE + 'tasks/', HTTP_X_ADMINCORE_TENANT=str(second.pk)).json()['data']['items'][0]['id'] == str(other.pk)
    membership.is_active = False
    membership.save(update_fields=['is_active'])
    assert client.get(BASE + 'tasks/', HTTP_X_ADMINCORE_TENANT=str(first.pk)).status_code == 403
    first.status = Tenant.STATUS_SUSPENDED
    first.save(update_fields=['status'])
    assert client.get(BASE + 'tasks/', HTTP_X_ADMINCORE_TENANT=str(first.pk)).status_code == 403
