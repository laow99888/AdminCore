"""只允许生成器隔离库执行；验证实际产物，不导入示例模块。"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Event
from types import SimpleNamespace
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections, transaction
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, NotFound
from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session
from apps.core.models import DataScopeGrant
from apps.work_assets.models import AssetRecord
from apps.work_assets.services import mutate
from apps.logs.models import OperationLog
from apps.permissions.models import Role, Permission, RolePermission, UserRole

assert settings.DATABASES['default']['NAME'] == 'codegen_fixture'
assert connections['default'].vendor == 'postgresql'
User = get_user_model(); suffix = uuid.uuid4().hex[:10]
actors = [User.objects.create_superuser('generated-race-' + suffix + str(number), password='Fixture#27835') for number in range(2)]
tokens = [issue_session(actor) for actor in actors]
URL = '/api/v1/work-assets/records/'


def race(method, path, values, same=False, key=None):
    barrier = Barrier(2)
    def execute(index):
        try:
            client = APIClient(HTTP_HOST='backend')
            client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(tokens[0 if same else index].access_token))
            barrier.wait(10)
            response = getattr(client, method)(path, values[index], format='json',
                **({'HTTP_IDEMPOTENCY_KEY': key} if key else {}))
            return response.status_code, response.json()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(execute, range(2)))


row = AssetRecord.objects.create(creator=actors[0], label='race')
results = race('patch', URL + str(row.pk) + '/', [{'version': 1, 'quantity': value} for value in (4, 5)])
row.refresh_from_db()
assert sorted(code for code, _ in results) == [200, 409] and row.version == 2
assert OperationLog.objects.filter(resource='work_assets', resource_id=str(row.pk)).count() == 1
payload = {'label': 'same-create', 'quantity': 1, 'available': True, 'version': 0}
results = race('post', URL, [payload, payload], same=True, key=suffix)
assert [code for code, _ in results] == [201, 201] and results[0][1] == results[1][1]
assert AssetRecord.objects.filter(label='same-create').count() == 1
assert OperationLog.objects.filter(resource='work_assets', resource_id=results[0][1]['data']['id']).count() == 1
results = race('delete', URL + str(row.pk) + '/', [{'version': 2}, {'version': 2}])
assert sorted(code for code, _ in results) == [200, 404]
assert OperationLog.objects.filter(resource='work_assets', resource_id=str(row.pk), action='delete').count() == 1

for boundary in ['account', 'session', 'permission', 'scope']:
    actor = User.objects.create_user('generated-wait-' + suffix + boundary, password='Fixture#27835')
    role = Role.objects.create(name='generated-wait-' + suffix + boundary)
    UserRole.objects.create(user=actor, role=role)
    for permission in Permission.objects.filter(code__startswith='work_assets:'):
        RolePermission.objects.create(role=role, permission=permission)
    token = issue_session(actor)
    row = AssetRecord.objects.create(creator=actor, label='retained')
    request = SimpleNamespace(user=actor, auth=token.access_token, META={'REMOTE_ADDR': '127.0.0.1'})
    locked, release = Event(), Event()
    def revoke():
        try:
            with transaction.atomic():
                current = User.objects.select_for_update().get(pk=actor.pk)
                if boundary == 'account':
                    current.is_active = False; current.save(update_fields=['is_active'])
                elif boundary == 'session':
                    AuthSession.objects.filter(pk=token['sid']).update(revoked_at=timezone.now())
                elif boundary == 'permission':
                    RolePermission.objects.filter(role=role, permission__code='work_assets:update').delete()
                else:
                    DataScopeGrant.objects.create(role=role, resource='work_assets', scope='custom')
                locked.set()
                assert release.wait(10)
        finally:
            connections.close_all()
    def write():
        try:
            try:
                mutate(request, 'update', {'version': 1, 'label': 'must not persist'}, row.pk)
            except (AuthenticationFailed, PermissionDenied, NotFound) as error:
                return error.status_code
            raise AssertionError('旧权限通过了等待后的写入')
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(revoke); assert locked.wait(10); second = pool.submit(write)
        try:
            try:
                second.result(timeout=0.25)
                raise AssertionError('没有等待用户行锁')
            except TimeoutError:
                pass
        finally:
            release.set()
        first.result(timeout=10)
        assert second.result(timeout=10) == {'account': 401, 'session': 401, 'permission': 403, 'scope': 404}[boundary]
    row.refresh_from_db()
    assert row.label == 'retained' and row.version == 1
    assert not OperationLog.objects.filter(resource='work_assets', resource_id=str(row.pk)).exists()
print('生成模块PostgreSQL并发/撤权七项通过')
