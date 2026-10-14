"""只允许在专属示例验收库执行：真实 SQL 竞争与等待后授权复核。"""
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Event
from types import SimpleNamespace
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections, transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, NotFound
from rest_framework.test import APIClient
from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session
from apps.core.models import DataScopeGrant
from apps.example.models import WorkItem
from apps.example.services import mutate
from apps.logs.models import OperationLog
from apps.permissions.models import Role, Permission, RolePermission, UserRole

assert settings.DATABASES['default']['NAME'] == 'example_fixture', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql'
User = get_user_model()
suffix = uuid.uuid4().hex[:12]
actors = [User.objects.create_superuser('example-race-' + suffix + str(n), password='Fixture#Secure27835') for n in range(2)]
tokens = [issue_session(actor) for actor in actors]
checks = []
URL = '/api/v1/example/items/'


def check(label, condition):
    assert condition, label
    checks.append(label)


def race(methods, path, values, same_actor=False, key=None):
    barrier = Barrier(2)
    def request(index):
        try:
            client = APIClient(HTTP_HOST='backend')
            client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(tokens[0 if same_actor else index].access_token))
            barrier.wait(10)
            response = getattr(client, methods[index])(path, values[index], format='json',
                **({'HTTP_IDEMPOTENCY_KEY': key} if key else {}))
            return response.status_code, response.json()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(request, range(2)))


row = WorkItem.objects.create(title='version race', creator=actors[0])
results = race(['patch', 'patch'], URL + str(row.pk) + '/', [{'version': 1, 'title': 'first'}, {'version': 1, 'title': 'second'}])
row.refresh_from_db()
check('不同操作者同版本编辑仅一次成功', sorted(code for code, _ in results) == [200, 409] and row.version == 2)
check('竞争编辑只有一条业务审计', OperationLog.objects.filter(resource='example', resource_id=str(row.pk)).count() == 1)
body = {'title': 'same key', 'version': 0}
results = race(['post', 'post'], URL, [body, body], same_actor=True, key=suffix + '-same')
check('同创建键双请求仅一个记录与一次审计', [code for code, _ in results] == [201, 201]
      and results[0][1] == results[1][1] and WorkItem.objects.filter(title='same key').count() == 1
      and OperationLog.objects.filter(resource='example', action='create', resource_id=results[0][1]['data']['id']).count() == 1)
results = race(['post', 'post'], URL, [{'title': 'different one', 'version': 0}, {'title': 'different two', 'version': 0}], same_actor=True, key=suffix + '-different')
check('同键不同载荷只有一次创建', sorted(code for code, _ in results) == [201, 409]
      and WorkItem.objects.filter(title__startswith='different ').count() == 1)
row = WorkItem.objects.create(title='delete race', creator=actors[0])
results = race(['delete', 'delete'], URL + str(row.pk) + '/', [{'version': 1}, {'version': 1}])
check('并发删除只有一次成功', sorted(code for code, _ in results) == [200, 404]
      and OperationLog.objects.filter(resource='example', resource_id=str(row.pk), action='delete').count() == 1)

for boundary in ['account', 'session', 'permission', 'scope']:
    actor = User.objects.create_user('example-wait-' + suffix + boundary, password='Fixture#Secure27835')
    role = Role.objects.create(name='example-wait-' + suffix + boundary)
    UserRole.objects.create(user=actor, role=role)
    for permission in Permission.objects.filter(code__startswith='example:'):
        RolePermission.objects.create(role=role, permission=permission)
    token = issue_session(actor)
    row = WorkItem.objects.create(title='retained original', creator=actor)
    request = SimpleNamespace(user=actor, auth=token.access_token, META={'REMOTE_ADDR': '127.0.0.1'})
    locked, release = Event(), Event()
    def hold_and_revoke():
        try:
            with transaction.atomic():
                current = User.objects.select_for_update().get(pk=actor.pk)
                if boundary == 'account':
                    current.is_active = False; current.save(update_fields=['is_active'])
                elif boundary == 'session':
                    AuthSession.objects.filter(pk=token['sid']).update(revoked_at=timezone.now())
                elif boundary == 'permission':
                    RolePermission.objects.filter(role=role, permission__code='example:update').delete()
                else:
                    DataScopeGrant.objects.create(role=role, resource='example', scope='custom')
                locked.set()
                assert release.wait(10)
        finally:
            connections.close_all()
    def waiting_write():
        try:
            try:
                mutate(request, 'update', {'version': 1, 'title': 'must not persist'}, row.pk)
            except (AuthenticationFailed, PermissionDenied, NotFound) as error:
                return error.status_code
            raise AssertionError('等待后仍使用旧授权')
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(hold_and_revoke)
        assert locked.wait(10)
        second = pool.submit(waiting_write)
        try:
            try:
                second.result(timeout=0.25)
                raise AssertionError('写入没有等待用户行锁')
            except TimeoutError:
                pass
        finally:
            release.set()
        first.result(timeout=10)
        code = second.result(timeout=10)
    row.refresh_from_db()
    check('等待后复核 ' + boundary, code == {'account': 401, 'session': 401, 'permission': 403, 'scope': 404}[boundary]
          and row.version == 1 and row.title == 'retained original'
          and not OperationLog.objects.filter(resource='example', resource_id=str(row.pk)).exists())

print('PostgreSQL 示例业务 ' + str(len(checks)) + ' 项竞争验收通过：' + '；'.join(checks), flush=True)
