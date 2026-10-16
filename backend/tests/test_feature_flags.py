from unittest.mock import patch
import uuid
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from apps.core.modules import MODULES, PRESETS, resolve_modules
from apps.core.contracts import validate_registry
from apps.feature_flags.manifest import MODULE
from apps.feature_flags.models import FeatureFlag
from apps.feature_flags.services import bucket, evaluate, feature_enabled
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole, Menu

pytestmark = pytest.mark.django_db
URL = '/api/v1/feature-flags/'


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'feature_flags')
    settings.ROOT_URLCONF = 'tests.feature_flags_urls'


def grant(user, codes=None):
    role = Role.objects.create(name='flags-' + str(user.pk))
    for resource, action, name, code in MODULE.permissions:
        permission, _ = Permission.objects.get_or_create(resource=resource, action=action, defaults={'name': name, 'code': code})
        if codes is None or code in codes:
            RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=user, role=role)
    return role


def create(client, **values):
    return client.post(URL + 'flags/', {'key': 'checkout.new', 'name': '新功能', 'version': 0, **values}, format='json')


def test_disabled_module_has_no_queries_and_gates_all_paths(admin_client, admin_user, settings):
    assert 'feature_flags' not in PRESETS['standard'] and 'feature_flags' not in PRESETS['minimal']
    validate_registry(MODULES)
    assert resolve_modules('minimal', 'feature_flags') == ('feature_flags',)
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'feature_flags')
    with CaptureQueriesContext(connection) as queries:
        assert feature_enabled('test', admin_user) is False
    assert len(queries) == 0
    assert create(admin_client).status_code == 404
    assert admin_client.post(URL + 'evaluate/', {'keys': ['test']}, format='json').status_code == 404


def test_create_update_versions_immutable_key_audit_and_delete(admin_client):
    response = create(admin_client)
    assert response.status_code == 201
    data = response.json()['data']
    assert not data['enabled'] and data['rollout'] == 0 and data['version'] == 1
    assert 'seed' not in data
    detail = URL + 'flags/' + data['id'] + '/'
    assert admin_client.get(detail)['Cache-Control'] == 'private, no-store'
    assert admin_client.patch(detail, {'enabled': True}, format='json').status_code == 400
    assert admin_client.patch(detail, {'enabled': True, 'version': 0}, format='json').status_code == 409
    assert admin_client.patch(detail, {'key': 'new.key', 'version': 1}, format='json').status_code == 400
    updated = admin_client.patch(detail, {'enabled': True, 'rollout': 5000, 'version': 1}, format='json')
    assert updated.status_code == 200 and updated.json()['data']['version'] == 2
    audit = OperationLog.objects.get(resource='feature_flag', action='update')
    assert audit.before_values['enabled'] is False and audit.after_values['enabled'] is True
    assert 'name' not in audit.after_values and 'description' not in audit.after_values
    assert admin_client.delete(detail, {'version': 1}, format='json').status_code == 409
    assert admin_client.delete(detail, {'version': 2}, format='json').status_code == 200
    assert not FeatureFlag.objects.exists()


@pytest.mark.parametrize('values', [
    {'key': 'bad key'}, {'key': 'UPPER'}, {'key': 'x' * 101}, {'name': ''},
    {'rollout': -1}, {'rollout': 10001}, {'rollout': 2.5}, {'version': 3},
    {'seed': str(uuid.uuid4())}, {'included_users': [str(uuid.uuid4())]},
    {'included_users': ['invalid']}, {'roles': [str(uuid.uuid4())]},
    {'excluded_users': [str(uuid.uuid4())] * 101},
])
def test_invalid_configuration_never_writes(admin_client, values):
    assert create(admin_client, **values).status_code in [400, 409]
    assert not FeatureFlag.objects.exists()


def test_members_cannot_read_rules_but_can_evaluate_only_themselves(member_client, member_user, admin_user):
    FeatureFlag.objects.create(key='test', name='private', enabled=True, included_users=[str(admin_user.pk)])
    assert member_client.get(URL + 'flags/').status_code == 403
    assert create(member_client).status_code == 403
    assert member_client.get(URL + 'targets/?kind=users').status_code == 403
    response = member_client.post(URL + 'evaluate/', {'keys': ['test', 'unknown']}, format='json')
    assert response.status_code == 200
    assert response.json()['data'] == [{'key': 'test', 'enabled': False}, {'key': 'unknown', 'enabled': False}]
    assert response['Cache-Control'] == 'private, no-store'
    assert member_client.post(URL + 'evaluate/', {'keys': ['test'], 'user_id': str(admin_user.pk)}, format='json').status_code == 400


@pytest.mark.parametrize('keys', [[], ['test', 'test'], ['bad key'], [f'test.{i}' for i in range(101)]])
def test_evaluation_boundaries(member_client, keys):
    assert member_client.post(URL + 'evaluate/', {'keys': keys}, format='json').status_code == 400


def test_target_inclusion_exclusion_role_revocation_and_master_switch(member_user):
    flag = FeatureFlag.objects.create(key='test', name='test', enabled=True)
    assert not feature_enabled('test', member_user)
    flag.included_users = [str(member_user.pk)]; flag.save()
    assert feature_enabled('test', member_user)
    flag.excluded_users = [str(member_user.pk)]; flag.save()
    assert not feature_enabled('test', member_user)
    flag.included_users = []; flag.excluded_users = []; flag.save()
    role = Role.objects.create(name='pilot')
    membership = UserRole.objects.create(user=member_user, role=role)
    flag.roles = [str(role.pk)]; flag.save()
    assert feature_enabled('test', member_user)
    role.is_active = False; role.save()
    assert not feature_enabled('test', member_user)
    role.is_active = True; role.save()
    membership.delete()
    assert not feature_enabled('test', member_user)
    flag.rollout = 10000; flag.save()
    assert feature_enabled('test', member_user)
    flag.enabled = False; flag.save()
    assert not feature_enabled('test', member_user)
    flag.enabled = True; flag.save()
    member_user.is_active = False; member_user.save()
    assert not feature_enabled('test', member_user)


def test_stable_rollout_membership_monotone_and_per_flag_seed():
    first = FeatureFlag(key='first', name='first')
    second = FeatureFlag(key='second', name='second')
    users = [uuid.uuid4() for _ in range(1000)]
    initial = {user for user in users if bucket(first, user) < 2500}
    expanded = {user for user in users if bucket(first, user) < 7500}
    assert initial < expanded and 150 < len(initial) < 350 and 650 < len(expanded) < 850
    assert [bucket(first, user) for user in users] == [bucket(first, user) for user in users]
    assert [bucket(first, user) for user in users] != [bucket(second, user) for user in users]


def test_batch_query_budget_constant_and_no_stale_policy(member_user):
    FeatureFlag.objects.bulk_create([FeatureFlag(key=f'test.{i}', name='test', enabled=True, rollout=10000) for i in range(100)])
    keys = [f'test.{i}' for i in range(100)]
    with CaptureQueriesContext(connection) as queries:
        assert all(evaluate(keys, member_user).values())
    assert len(queries) == 3
    FeatureFlag.objects.filter(key='test.1').update(enabled=False)
    assert not evaluate(keys, member_user)['test.1']


def test_permissions_rechecked_before_idempotent_replay(member_client, member_user):
    role = grant(member_user)
    values = {'key': 'idempotent', 'name': 'once', 'version': 0}
    first = member_client.post(URL + 'flags/', values, format='json', HTTP_IDEMPOTENCY_KEY='flags-once')
    second = member_client.post(URL + 'flags/', values, format='json', HTTP_IDEMPOTENCY_KEY='flags-once')
    assert first.status_code == second.status_code == 201 and first.json() == second.json()
    assert second['Idempotency-Replayed'] == 'true'
    assert FeatureFlag.objects.count() == 1 and OperationLog.objects.filter(resource='feature_flag').count() == 1
    role.is_active = False; role.save()
    assert member_client.post(URL + 'flags/', values, format='json', HTTP_IDEMPOTENCY_KEY='flags-once').status_code == 403


def test_target_validation_search_and_selected_limit(admin_client, admin_user, member_user):
    values = {'included_users': [str(member_user.pk), str(member_user.pk)]}
    assert create(admin_client, **values).status_code == 400
    values = {'included_users': [str(member_user.pk)], 'excluded_users': [str(member_user.pk)]}
    assert create(admin_client, **values).status_code == 400
    assert admin_client.get(URL + 'targets/?kind=unknown').status_code == 400
    assert admin_client.get(URL + 'targets/?kind=users&selected=bad').status_code == 400
    response = admin_client.get(URL + 'targets/', {'kind': 'users', 'search': 'mem', 'selected': str(admin_user.pk)})
    assert response.status_code == 200
    assert {row['id'] for row in response.json()['data']} == {str(admin_user.pk), str(member_user.pk)}
    assert set(response.json()['data'][0]) == {'id', 'label'}


def test_audit_failure_rolls_back(admin_client):
    with patch('apps.feature_flags.services.write_audit', side_effect=RuntimeError('fixture')):
        assert create(admin_client).status_code == 500
    assert not FeatureFlag.objects.exists()


def test_list_queries_filter_and_explicit_manifest_seeding(admin_client, admin_user):
    from io import StringIO
    admin_user.set_password('BootstrapFixture#987654321'); admin_user.save()
    call_command('bootstrap_admincore', stdout=StringIO())
    admin_client.force_authenticate(user=admin_user)
    menu = Menu.objects.get(path='/system/feature-flags')
    assert menu.permission.code == 'feature_flag:read'
    assert create(admin_client).status_code == 201
    assert admin_client.get(URL + 'flags/?search=checkout').json()['data']['pagination']['total'] == 1
    assert admin_client.get(URL + 'flags/?enabled=true').json()['data']['pagination']['total'] == 0
    assert admin_client.get(URL + 'flags/?ordering=seed').status_code == 400


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_updates_cannot_overwrite_each_other(settings):
    if connection.vendor != 'postgresql':
        pytest.skip('行锁验收只在独立 PostgreSQL 执行')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections
    from rest_framework.test import APIClient
    first = get_user_model().objects.create_superuser('flags_writer_one', password='fixture')
    second = get_user_model().objects.create_superuser('flags_writer_two', password='fixture')
    flag = FeatureFlag.objects.create(key='concurrent', name='original')
    barrier = Barrier(2)
    def write(user):
        close_old_connections()
        try:
            client = APIClient(); client.force_authenticate(user=user)
            barrier.wait(timeout=10)
            return client.patch(URL + f'flags/{flag.pk}/', {'name': user.username, 'version': 1}, format='json').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, [first, second]))
    assert sorted(outcomes) == [200, 409]
    flag.refresh_from_db()
    assert flag.version == 2 and flag.name in {first.username, second.username}
    assert OperationLog.objects.filter(resource='feature_flag', action='update').count() == 1
