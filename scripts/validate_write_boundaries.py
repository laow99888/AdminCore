"""仅 foundation 的真实 PostgreSQL 容量边界及锁等待撤权验收。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import connection, connections, transaction
from rest_framework.test import APIClient

from apps.auth_app.sessions import issue_session
from apps.core.models import DataScopeGrant, Department, OrganizationMembership, Post
from apps.files.models import FileModel
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.tasks.models import ImportBatch, ImportExecution, TaskRecord
from apps.tasks.reliability import policy
from apps.users.views import UserViewSet

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connection.vendor == 'postgresql', '必须使用 PostgreSQL'
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    assert cursor.fetchone()[0] == 'foundation'

User = get_user_model()
prefix = 'write_boundary_' + uuid4().hex[:12]
admin = User.objects.create_superuser(prefix + '_admin', password=uuid4().hex + uuid4().hex,
                                     must_change_password=False)


def jwt_client(user):
    token = issue_session(user)
    client = APIClient(HTTP_HOST='localhost')
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    return client


client = jwt_client(admin)
rows = User.objects.bulk_create([User(username=prefix + '_' + str(index), password='!',
    must_change_password=False) for index in range(1000)])
identifiers = [str(row.pk) for row in reversed(rows)]
started = monotonic()
response = client.post('/api/v1/users/bulk_action/',
    {'action': 'deactivate', 'user_ids': identifiers}, format='json')
assert response.status_code == 200, response.status_code
assert response.json()['data'] == {'atomic': True, 'succeeded': 1000, 'failed': 0,
    'results': [{'id': identifier, 'status': 200} for identifier in identifiers]}
assert User.objects.filter(pk__in=identifiers, is_active=False, profile_version=2).count() == 1000
assert OperationLog.objects.filter(resource='user', resource_id__in=identifiers, action='deactivate').count() == 1000
print('通过：真实JWT/PG 1000项整批写入，响应顺序、版本和1000条审计一致；耗时 %.2f 秒' % (monotonic()-started), flush=True)
response = client.post('/api/v1/users/bulk_action/',
    {'action': 'activate', 'user_ids': identifiers + [str(uuid4())]}, format='json')
assert response.status_code == 400
assert User.objects.filter(pk__in=identifiers, is_active=False, profile_version=2).count() == 1000
print('通过：1001项在写入前拒绝，原1000项状态与版本不变', flush=True)


def race(kind):
    actor = User.objects.create_user(prefix + '_' + kind, password=uuid4().hex + uuid4().hex,
                                    must_change_password=False)
    target = User.objects.create_user(prefix + '_target_' + kind, password=None)
    role = Role.objects.create(name=prefix + '_role_' + kind)
    UserRole.objects.create(user=actor, role=role)
    permission, _ = Permission.objects.get_or_create(code='user:update', defaults={
        'name': '更新用户', 'resource': 'user', 'action': 'update'})
    assignment = RolePermission.objects.create(role=role, permission=permission)
    grant = DataScopeGrant.objects.create(role=role, resource='user', scope='all')
    if kind == 'department':
        first = Department.objects.create(name=prefix + '_first')
        second = Department.objects.create(name=prefix + '_second')
        grant.scope = 'department'
        grant.save(update_fields=['scope'])
        OrganizationMembership.objects.create(user=actor, department=first)
        membership = OrganizationMembership.objects.create(user=target, department=first)
    api = jwt_client(actor)
    entered = Event()
    original = UserViewSet._authorize_locked

    def observed(view, targets=(), extra_codes=()):
        # Scheduling hook only; authorization and row locking remain production code.
        entered.set()
        return original(view, targets, extra_codes)

    def write():
        try:
            return api.post('/api/v1/users/bulk_action/', {'action': 'deactivate',
                'user_ids': [str(target.pk)]}, format='json')
        finally:
            connections.close_all()

    with patch.object(UserViewSet, '_authorize_locked', observed), ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            User.objects.select_for_update().get(pk=actor.pk)
            future = pool.submit(write)
            assert entered.wait(timeout=10), '请求必须先通过入口JWT和权限检查'
            if kind == 'permission':
                assignment.delete()
            elif kind == 'scope':
                grant.scope = 'self'
                grant.save(update_fields=['scope'])
            elif kind == 'department':
                membership.department = second
                membership.save(update_fields=['department'])
            else:
                User.objects.filter(pk=actor.pk).update(session_version=actor.session_version + 1)
        response = future.result(timeout=25)
    assert response.status_code == (401 if kind == 'session' else 403), response.status_code
    target.refresh_from_db()
    assert target.is_active and target.profile_version == 1
    assert not OperationLog.objects.filter(resource='user', resource_id=str(target.pk)).exists()
    print('通过：真实JWT/PG 请求进入后锁等待期间 ' + kind + ' 变更，重新授权拒绝且无目标变更', flush=True)


for kind in ('permission', 'scope', 'department', 'session'):
    race(kind)

# Exercise the registered executor on real storage/PG without competing with the live
# outbox consumer. Foundation separately tests the actual HTTP -> Redis -> worker chain.
from apps.data_io.tasks import run_data_import
from apps.data_io.execution import digest

for count in (5000, 5001):
    content = ('code,name\n' + ''.join(prefix + '_p_' + str(count) + '_' + str(index)
        + ',Boundary ' + str(index) + '\n' for index in range(count))).encode()
    source = FileModel.objects.create(original_name='boundary.csv', file_type='csv',
        size=len(content), content_type='text/csv', uploader=admin, purpose='import',
        file=ContentFile(content, name=prefix + '_' + str(count) + '.csv'))
    record = TaskRecord.objects.create(name='隔离容量边界', task_type='import',
        related_resource='posts', creator=admin, result={'file_id': str(source.pk)})
    batch = ImportBatch.objects.create(source=source, source_sha256=digest(source.file),
        resource='posts', active_record=record)
    session = issue_session(admin)
    ImportExecution.objects.create(record=record, batch=batch, policy=policy('import'),
        session_version=admin.session_version, session_id=session['sid'])
    started = monotonic()
    run_data_import(str(record.pk))
    record.refresh_from_db()
    if count == 5000:
        assert record.status == 'success', (record.status, record.error)
        assert (record.result['created'], record.result['failed'], record.result['processed']) == (5000, 0, 5000)
        assert batch.receipts.filter(created=True).count() == 5000
        assert Post.objects.filter(code__startswith=prefix + '_p_5000_', is_active=False).count() == 5000
        assert OperationLog.objects.filter(task_record_id=record.pk, resource='post', description='import_row_created').count() == 5000
    else:
        assert record.status == 'failed' and record.error == 'import_row_limit_5000'
        assert not batch.receipts.exists()
        assert not Post.objects.filter(code__startswith=prefix + '_p_5001_').exists()
    print('通过：真实PG注册导入执行器 ' + str(count) + '行边界及账本/审计/默认停用；耗时 %.2f 秒' % (monotonic()-started), flush=True)
    # Only this script's generated source key, never original/user media.
    source.file.delete(save=False)
    source.delete()

print('通过：本段边界夹具仅存在于即将整体移除的 foundation 独立库', flush=True)
