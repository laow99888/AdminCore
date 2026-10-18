"""真实接口验收：机器主体独立于管理者密码与个人生命周期。"""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError

from apps.api_credentials.models import APICredential, ServiceIdentity
from apps.auth_app.sessions import issue_session, validate_session
from apps.core.models import DataScopeGrant, Tenant, TenantMembership
from apps.core.tenancy import clear_current_tenant, tenant_context
from apps.permissions.models import Permission, Role, RolePermission

pytestmark = pytest.mark.django_db
BASE = '/api/v1/api-credentials/service-identities/'
PASSWORD = 'Admin#12345'


@pytest.fixture(autouse=True)
def identity_modules(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'api_credentials', 'tasks')
    clear_current_tenant()
    yield
    clear_current_tenant()


@pytest.fixture
def reader_role():
    row = Role.objects.create(name='machine-readers')
    permission, _ = Permission.objects.get_or_create(code='task:read', defaults={
        'resource': 'task', 'action': 'read', 'name': 'read tasks'})
    RolePermission.objects.create(role=row, permission=permission)
    DataScopeGrant.objects.create(role=row, resource='task', scope='self')
    return row


def create(manager, role):
    result = manager.post(BASE, {'name': 'ERP 集成', 'role_ids': [str(role.pk)], 'current_password': PASSWORD}, format='json')
    assert result.status_code == 201, result.content
    return ServiceIdentity.objects.select_related('user').get(pk=result.json()['data']['id'])


def issue(manager, row):
    result = manager.post(BASE + f'{row.pk}/issue/', {'name': 'ERP只读', 'scopes': ['task:read'],
        'expires_at': (timezone.now() + timedelta(days=7)).isoformat(), 'current_password': PASSWORD}, format='json')
    assert result.status_code == 201, result.content
    data = result.json()['data']
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='ApiToken ' + data['token'])
    return client, data


def test_identity_is_independent_of_creator_and_preserves_scope(admin_user, admin_client, reader_role):
    from apps.tasks.models import TaskRecord
    row = create(admin_client, reader_role)
    assert row.user.is_service_account and not row.user.has_usable_password()
    assert not row.user.is_staff and not row.user.is_superuser and not row.user.email
    client, data = issue(admin_client, row)
    own = TaskRecord.objects.create(creator=row.user, name='机器任务')
    TaskRecord.objects.create(creator=admin_user, name='其他任务')
    url = '/api/v1/api-credentials/tasks/'
    assert [value['id'] for value in client.get(url).json()['data']['items']] == [str(own.pk)]
    assert client.get('/api/v1/tasks/').status_code == 401
    assert client.get(BASE).status_code == 401
    assert client.post(url, {}, format='json').status_code == 403
    assert data['token'] not in repr(APICredential.objects.get(pk=data['id']).__dict__)
    admin_user.set_password('replacement-test-password')
    admin_user.is_active = False
    admin_user.save()
    assert client.get(url).status_code == 200
    admin_user.delete()
    row.refresh_from_db()
    assert row.created_by_id is None
    assert client.get(url).status_code == 200


@pytest.mark.parametrize('change,status', [('disable', 401), ('permission', 403), ('role', 403), ('revoke', 401), ('tenant-mode', 401)])
def test_identity_authorization_is_current(admin_client, reader_role, settings, change, status):
    row = create(admin_client, reader_role)
    client, data = issue(admin_client, row)
    if change == 'disable':
        response = admin_client.patch(BASE + f'{row.pk}/', {'version': 1, 'is_active': False, 'current_password': PASSWORD}, format='json')
        assert response.status_code == 200, response.content
    elif change == 'permission':
        RolePermission.objects.filter(role=reader_role).delete()
    elif change == 'role':
        reader_role.is_active = False
        reader_role.save()
    elif change == 'tenant-mode':
        settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    else:
        response = admin_client.post(BASE + f'{row.pk}/revoke/', {'credential_id': data['id'], 'version': 1, 'current_password': PASSWORD}, format='json')
        assert response.status_code == 200, response.content
    assert client.get('/api/v1/api-credentials/tasks/').status_code == status


def test_disabled_identity_reenable_cannot_revive_old_token(admin_client, reader_role):
    row = create(admin_client, reader_role)
    client, _ = issue(admin_client, row)
    for version, active in [(1, False), (2, True)]:
        assert admin_client.patch(BASE + f'{row.pk}/', {'version': version, 'is_active': active, 'current_password': PASSWORD}, format='json').status_code == 200
    assert client.get('/api/v1/api-credentials/tasks/').status_code == 401
    assert issue(admin_client, row)[0].get('/api/v1/api-credentials/tasks/').status_code == 200


def test_machine_rotation_conflict_and_current_rights(admin_client, reader_role):
    row = create(admin_client, reader_role)
    client, data = issue(admin_client, row)
    body = {'credential_id': data['id'], 'version': 1, 'current_password': PASSWORD}
    rotated = admin_client.post(BASE + f'{row.pk}/rotate/', body, format='json')
    assert rotated.status_code == 200, rotated.content
    assert rotated.json()['data']['version'] == 2
    assert client.get('/api/v1/api-credentials/tasks/').status_code == 401
    next_client = APIClient(HTTP_AUTHORIZATION='ApiToken ' + rotated.json()['data']['token'])
    assert next_client.get('/api/v1/api-credentials/tasks/').status_code == 200
    assert admin_client.post(BASE + f'{row.pk}/rotate/', body, format='json').status_code == 409
    RolePermission.objects.filter(role=reader_role).delete()
    body['version'] = 2
    assert admin_client.post(BASE + f'{row.pk}/rotate/', body, format='json').status_code == 403


def test_personal_crud_and_password_entry_points_cannot_convert_machine(admin_user, admin_client, member_user, reader_role):
    from apps.auth_app import recovery
    from apps.sso.service import current_identity
    row = create(admin_client, reader_role)
    for path in (f'/api/v1/users/{row.pk}/', f'/api/v1/users/{row.pk}/reset_password/'):
        method = admin_client.patch if path.endswith(str(row.pk) + '/') else admin_client.post
        assert method(path, {'version': 1, 'password': 'Pretend#123456', 'current_password': PASSWORD}, format='json').status_code == 404
    assert str(row.pk) not in admin_client.get('/api/v1/users/').content.decode()
    result = admin_client.post('/api/v1/users/', {'username': 'illegal-machine', 'password': 'Pretend#123456', 'is_service_account': True}, format='json')
    assert result.status_code == 400
    with pytest.raises(ModelValidationError):
        row.user.set_password('Pretend#123456')
    with pytest.raises(ModelValidationError):
        row.user.is_staff = True
        row.user.save()
    row.user.refresh_from_db()
    with pytest.raises(ModelValidationError):
        row.user.is_service_account = False
        row.user.save()
    member_user.is_service_account = True
    with pytest.raises(ModelValidationError):
        member_user.save()
    row.user.refresh_from_db()
    with pytest.raises(AuthenticationFailed):
        issue_session(row.user)
    with pytest.raises(AuthenticationFailed):
        validate_session(None, row.user, {})
    with pytest.raises(AuthenticationFailed):
        current_identity(SimpleNamespace(), row.user, SimpleNamespace())
    with pytest.raises(ValidationError):
        recovery.create_challenge(row.user, 'reset', None)
    assert not recovery.challenge_valid(None, row.user)
    assert APIClient().post('/api/v1/auth/login/', {'username': row.user.username, 'password': 'Pretend#123456'}, format='json').status_code == 401


@pytest.mark.parametrize('field,value', [('is_staff', True), ('is_service_account', False), ('tenant_id', None), ('password', 'x')])
def test_identity_api_rejects_extra_fields(admin_client, reader_role, field, value):
    row = create(admin_client, reader_role)
    assert admin_client.patch(BASE + f'{row.pk}/', {'version': 1, field: value, 'current_password': PASSWORD}, format='json').status_code == 400


def test_only_current_admin_and_readonly_roles_can_manage(admin_client, member_client, reader_role):
    assert member_client.get(BASE).status_code == 403
    reader_role.permissions.create(permission=Permission.objects.create(code='task:create', name='write', resource='task', action='create'))
    result = admin_client.post(BASE, {'name': 'bad role', 'role_ids': [str(reader_role.pk)], 'current_password': PASSWORD}, format='json')
    assert result.status_code == 403
    assert not ServiceIdentity.objects.exists()


@pytest.mark.parametrize('change,status', [('switch', 403), ('membership', 401), ('tenant', 401)])
def test_machine_fixed_tenant_membership_and_lifecycle(admin_user, admin_client, reader_role, settings, change, status):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(name='机器租户', slug='machine-tenant')
    second = Tenant.objects.create(name='其他租户', slug='machine-other')
    Role.all_objects.filter(pk=reader_role.pk).update(tenant=tenant)
    RolePermission.all_objects.filter(role=reader_role).update(tenant=tenant)
    DataScopeGrant.all_objects.filter(role=reader_role).update(tenant=tenant)
    admin_client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(issue_session(admin_user).access_token), HTTP_X_ADMINCORE_TENANT=str(tenant.pk))
    with tenant_context(tenant.pk):
        row = create(admin_client, reader_role)
        client, _ = issue(admin_client, row)
    assert client.get('/api/v1/api-credentials/tasks/').status_code == 200
    if change == 'switch':
        client.credentials(HTTP_AUTHORIZATION=client._credentials['HTTP_AUTHORIZATION'], HTTP_X_ADMINCORE_TENANT=str(second.pk))
    elif change == 'membership':
        TenantMembership.objects.filter(user=row.user).update(is_active=False)
    else:
        tenant.status = Tenant.STATUS_SUSPENDED
        tenant.save()
    assert client.get('/api/v1/api-credentials/tasks/').status_code == status

def test_even_fabricated_signed_session_cannot_interactively_authenticate_machine(admin_client, admin_user, reader_role, settings):
    from django.contrib import admin
    from django.contrib.auth.hashers import make_password
    from django.test import RequestFactory
    from rest_framework_simplejwt.utils import get_md5_hash_password
    from apps.auth_app.admin import UserAdmin
    from apps.auth_app.models import AuthSession
    from apps.auth_app.serializers import RefreshTokenSerializer
    from apps.auth_app.sessions import SessionRefreshToken, active_sessions
    from apps.sso.service import current_identity
    row = create(admin_client, reader_role)
    # 故意绕过模型守卫，模拟受损数据；鉴权仍须根据不可交互身份标志拒绝。
    get_user_model().objects.filter(pk=row.pk).update(password=make_password('Pretend#123456'))
    row.user.refresh_from_db()
    token = SessionRefreshToken.for_user(row.user)
    now = timezone.now()
    session = AuthSession.objects.create(user=row.user, session_version=row.user.session_version,
        password_hash=get_md5_hash_password(row.user.password), refresh_jti=token['jti'],
        created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=1))
    token['sid'] = str(session.pk)
    token['session_version'] = row.user.session_version
    token['hash_password'] = session.password_hash
    client = APIClient(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    assert client.get('/api/v1/auth/me/').status_code == 401
    assert not active_sessions().filter(pk=session.pk).exists()
    with pytest.raises(TokenError):
        RefreshTokenSerializer().rotate(token)
    with pytest.raises(AuthenticationFailed):
        current_identity(SimpleNamespace(), row.user, SimpleNamespace())
    assert APIClient().post('/api/v1/auth/login/', {'username': row.user.username, 'password': 'Pretend#123456'}, format='json').status_code == 401
    request = RequestFactory().get('/admin/')
    request.user = admin_user
    model_admin = UserAdmin(get_user_model(), admin.site)
    assert model_admin.get_object(request, str(row.pk)) is None
    # 即使损坏的密码可验证，恢复入口也不创建挑战。
    from apps.auth_app.recovery import request_reset
    from apps.auth_app.models import EmailChallenge
    request_reset(request, row.user.username, 'any@example.com')
    assert not EmailChallenge.objects.filter(user=row.user).exists()


def test_service_credentials_are_not_visible_or_operable_in_personal_area(admin_client, reader_role):
    row = create(admin_client, reader_role)
    _, credential = issue(admin_client, row)
    personal = '/api/v1/api-credentials/credentials/'
    assert credential['id'] not in admin_client.get(personal).content.decode()
    assert admin_client.post(personal + credential['id'] + '/revoke/', {'current_password': PASSWORD}, format='json').status_code == 404
    assert admin_client.post(BASE + f'{row.pk}/rotate/', {'credential_id': credential['id'], 'version': 1, 'current_password': 'wrong'}, format='json').status_code == 403
    assert APICredential.objects.get(pk=credential['id']).version == 1


def test_disabled_or_expired_module_and_credential_cannot_authenticate_machine(admin_client, reader_role, settings):
    row = create(admin_client, reader_role)
    client, credential = issue(admin_client, row)
    APICredential.objects.filter(pk=credential['id']).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert client.get('/api/v1/api-credentials/tasks/').status_code == 401
    settings.ADMINCORE_MODULES = tuple(value for value in settings.ADMINCORE_MODULES if value != 'api_credentials')
    assert admin_client.get(BASE).status_code == 404
    assert client.get('/api/v1/api-credentials/tasks/').status_code == 404


def test_human_bulk_personnel_notifications_and_role_forms_exclude_machine(admin_client, admin_user, reader_role, settings):
    from django.contrib import admin
    from django.test import RequestFactory
    from apps.core.personnel import candidates
    from apps.core.appointments import check_person
    from apps.core.organization_serializers import MembershipSerializer, DepartmentSerializer
    from apps.core.post_views import UserPostSerializer
    from apps.core.tenant_serializers import TenantMembershipSerializer
    from apps.notifications.models import Notification
    from apps.notifications.serializers import NotificationCreateSerializer
    from apps.permissions.models import UserRole
    from apps.permissions.serializers import UserRoleSerializer
    from apps.permissions.admin import UserRoleAdmin
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'notifications')
    row = create(admin_client, reader_role)
    for action in ('activate', 'deactivate', 'delete'):
        response = admin_client.post('/api/v1/users/bulk_action/', {'user_ids': [str(row.pk)], 'action': action}, format='json')
        assert response.status_code == 403, response.content
        row.refresh_from_db()
        assert row.user.is_active
    assert not candidates(admin_user).filter(pk=row.pk).exists()
    for serializer in (MembershipSerializer(), UserPostSerializer(), TenantMembershipSerializer(), UserRoleSerializer()):
        with pytest.raises(ValidationError):
            serializer.validate_user(row.user)
    with pytest.raises(ValidationError):
        check_person(row.user, None)
    with pytest.raises(ValidationError):
        DepartmentSerializer().validate_leader(row.user)
    assert not NotificationCreateSerializer(data={'recipient_ids': [str(row.pk)], 'title': 'machine'}).is_valid()
    assert Notification.push([row.pk], 'machine') == 0
    request = RequestFactory().get('/admin/')
    request.user = admin_user
    model_admin = UserRoleAdmin(UserRole, admin.site)
    assert not model_admin.get_queryset(request).filter(user=row.user).exists()
    field = model_admin.formfield_for_foreignkey(UserRole._meta.get_field('user'), request)
    assert not field.queryset.filter(pk=row.pk).exists()


def test_tenant_admin_role_cannot_issue_or_expand_machine_scope(admin_client, member_client, member_user, reader_role, settings):
    from apps.permissions.models import UserRole
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    tenant = Tenant.objects.create(name='管理者租户', slug='tenant-admin-machine')
    # 租户级admin和拥有manage权限，仍然不是系统管理员。
    TenantMembership.objects.create(tenant=tenant, user=member_user, role='admin')
    manage = Permission.objects.create(code='api_credential:manage', resource='api_credential', action='manage', name='manage')
    role = Role.all_objects.create(name='tenant-admin', tenant=tenant)
    RolePermission.all_objects.create(role=role, permission=manage, tenant=tenant)
    UserRole.all_objects.create(user=member_user, role=role, tenant=tenant)
    member_client.credentials(HTTP_AUTHORIZATION=member_client._credentials['HTTP_AUTHORIZATION'], HTTP_X_ADMINCORE_TENANT=str(tenant.pk))
    result = member_client.post(BASE, {'name': 'escalation', 'role_ids': [str(reader_role.pk)], 'current_password': 'Member#12345'}, format='json')
    assert result.status_code == 403
    assert not ServiceIdentity.objects.exists()


def parallel_client(headers, method, path, body):
    from django.db import connections
    connections.close_all()
    try:
        client = APIClient()
        client.credentials(**headers)
        return getattr(client, method)(path, body, format='json')
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_pg_two_admin_rotations_share_owner_lock_and_one_version_wins(admin_client, admin_user, reader_role):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import connection
    if connection.vendor != 'postgresql':
        pytest.skip('真实行锁竞态仅PostgreSQL')
    row = create(admin_client, reader_role)
    client, credential = issue(admin_client, row)
    other = get_user_model().objects.create_superuser('machine-second-admin', '', PASSWORD)
    other_token = str(issue_session(other).access_token)
    first_headers = dict(admin_client._credentials)
    second_headers = {'HTTP_AUTHORIZATION': 'Bearer ' + other_token}
    barrier = Barrier(2)
    body = {'credential_id': credential['id'], 'version': 1, 'current_password': PASSWORD}
    def rotate(headers):
        barrier.wait(timeout=10)
        return parallel_client(headers, 'post', BASE + f'{row.pk}/rotate/', body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(rotate, [first_headers, second_headers]))
    assert sorted(response.status_code for response in results) == [200, 409]
    winner = next(response for response in results if response.status_code == 200)
    assert client.get('/api/v1/api-credentials/tasks/').status_code == 401
    current = APIClient(HTTP_AUTHORIZATION='ApiToken ' + winner.json()['data']['token'])
    assert current.get('/api/v1/api-credentials/tasks/').status_code == 200
    assert APICredential.objects.get(pk=credential['id']).version == 2


@pytest.mark.django_db(transaction=True)
def test_pg_revoke_waits_for_current_owner_transaction_then_denies_next_request(admin_client, reader_role):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import connection, connections, transaction
    if connection.vendor != 'postgresql':
        pytest.skip('真实行锁竞态仅PostgreSQL')
    row = create(admin_client, reader_role)
    client, credential = issue(admin_client, row)
    started = Event()
    state = {}
    headers = dict(admin_client._credentials)
    # 并行函数须保留记录PID的同一真实连接；否则锁证据会指向已关闭连接。
    def locked_revoke():
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                state['pid'] = cursor.fetchone()[0]
            started.set()
            other = APIClient(); other.credentials(**headers)
            return other.post(BASE + f'{row.pk}/revoke/', {'credential_id': credential['id'], 'version': 1, 'current_password': PASSWORD}, format='json')
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=row.pk)
            pending = pool.submit(locked_revoke)
            assert started.wait(10)
            deadline = time.monotonic() + 10
            observed = False
            while time.monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s', [state['pid']])
                    result = cursor.fetchone()
                if result and result[0] == 'Lock':
                    observed = True
                    break
                time.sleep(.02)
            assert observed, '撤销请求必须真实等待正在进行的机器主体事务'
            assert not pending.done()
            assert client.get('/api/v1/api-credentials/tasks/').status_code == 200
        response = pending.result(timeout=15)
    assert response.status_code == 200, response.content
    assert client.get('/api/v1/api-credentials/tasks/').status_code == 401


def test_read_role_pollution_fails_closed_even_if_read_permission_remains(admin_client, reader_role):
    row = create(admin_client, reader_role)
    client, _ = issue(admin_client, row)
    permission = Permission.objects.create(code='user:update', name='write users', resource='user', action='update')
    RolePermission.objects.create(role=reader_role, permission=permission)
    assert client.get('/api/v1/api-credentials/tasks/').status_code == 403
    assert client.post('/api/v1/users/', {}, format='json').status_code == 401


def test_shared_write_and_admin_session_forms_reject_machine_even_without_request_auth(admin_client, reader_role):
    from django.db import transaction
    from apps.auth_app.admin import MFAAdminAuthenticationForm
    from apps.auth_app.write_authorization import authorize_write
    row = create(admin_client, reader_role)
    with transaction.atomic(), pytest.raises(AuthenticationFailed):
        authorize_write(SimpleNamespace(user=row.user, auth=None))
    # 表单必须按身份标志拒绝，不能仅依赖正常数据中staff=False。
    row.user.is_staff = True
    with pytest.raises(ModelValidationError):
        MFAAdminAuthenticationForm().confirm_login_allowed(row.user)


@pytest.mark.django_db(transaction=True)
def test_pg_global_machine_quota_is_atomic_between_two_administrators(admin_client, admin_user, reader_role):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import connection
    if connection.vendor != 'postgresql':
        pytest.skip('全局配额并发仅PostgreSQL')
    # 模拟已有99个机器主体，无须99次密码确认；约束与真实模型完全相同。
    for index in range(99):
        user = get_user_model()(username=f'quota_machine_{index}', is_service_account=True)
        user.set_unusable_password(); user.save()
        ServiceIdentity.objects.create(user=user, name=f'quota {index}', created_by=admin_user)
    second = get_user_model().objects.create_superuser('quota-second-admin', '', PASSWORD)
    headers = [dict(admin_client._credentials), {'HTTP_AUTHORIZATION': 'Bearer ' + str(issue_session(second).access_token)}]
    barrier = Barrier(2)
    def create_one(auth):
        barrier.wait(timeout=10)
        return parallel_client(auth, 'post', BASE, {'name': 'last-slot', 'role_ids': [str(reader_role.pk)], 'current_password': PASSWORD})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create_one, headers))
    assert sorted(response.status_code for response in results) == [201, 400]
    assert ServiceIdentity.objects.count() == 100
