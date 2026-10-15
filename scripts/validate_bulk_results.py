"""只在 foundation 隔离 PostgreSQL 验证用户批量结果及事务边界。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from rest_framework.test import APIClient

from apps.core.models import DataScopeGrant
from apps.example.models import WorkItem
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
User = get_user_model()
actor = User.objects.get(username='admin')
suffix = uuid4().hex[:12]
targets = [User.objects.create_user('bulk-' + suffix + '-' + str(index)) for index in range(2)]
identifiers = [str(row.pk) for row in targets]
URL = '/api/v1/users/bulk_action/'


def client(user=actor):
    api = APIClient(HTTP_HOST='localhost')
    api.force_authenticate(user)
    return api


def verify(response, submitted, code):
    assert response.status_code == code
    assert response.json()['data'] == {
        'atomic': True, 'succeeded': len(submitted) if code == 200 else 0,
        'failed': 0 if code == 200 else len(submitted),
        'results': [{'id': identifier, 'status': code} for identifier in submitted],
    }


barrier = Barrier(2)


def concurrent_change(action):
    try:
        submitted = identifiers if action == 'activate' else list(reversed(identifiers))
        barrier.wait(timeout=10)
        response = client().post(URL, {'action': action, 'user_ids': submitted}, format='json',
            HTTP_X_REQUEST_ID='bulk-pg-' + suffix + '-' + action)
        verify(response, submitted, 200)
    finally:
        connections.close_all()


with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(concurrent_change, ['activate', 'deactivate']))
assert len(set(User.objects.filter(pk__in=identifiers).values_list('is_active', flat=True))) == 1
for identifier in identifiers:
    logs = list(OperationLog.objects.filter(resource='user', resource_id=identifier,
        request_id__startswith='bulk-pg-' + suffix).order_by('created_at', 'id'))
    assert len(logs) == 2 and logs[0].after_values == logs[1].before_values
    assert logs[1].after_values['is_active'] == User.objects.get(pk=identifier).is_active
for action in ['activate', 'deactivate']:
    summary = OperationLog.objects.get(request_id='bulk-pg-' + suffix + '-' + action, resource_id='')
    submitted = identifiers if action == 'activate' else list(reversed(identifiers))
    assert summary.batch_results == [{'id': identifier, 'status': 200} for identifier in submitted]
print('通过：PostgreSQL 反序重叠批量写入整批串行、前后值连续及响应/审计一致', flush=True)

WorkItem.objects.create(title='保护批量删除-' + suffix, creator=targets[0])
verify(client().post(URL, {'action': 'delete', 'user_ids': identifiers}, format='json'), identifiers, 409)
assert User.objects.filter(pk__in=identifiers).count() == 2
assert not OperationLog.objects.filter(resource='user', resource_id__in=identifiers, action='delete').exists()
print('通过：PostgreSQL 真实受保护关联使整批删除回滚且逐项均报告未提交', flush=True)

before = list(User.objects.filter(pk__in=identifiers).order_by('pk').values_list('is_active', flat=True))
from apps.logs.audit import write_audit


def fail_after_audit(**kwargs):
    write_audit(**kwargs)
    raise RuntimeError('isolated audit fixture')


with patch('apps.logs.audit.write_audit', side_effect=fail_after_audit):
    verify(client().post(URL, {'action': 'deactivate' if before[0] else 'activate', 'user_ids': identifiers}, format='json',
        HTTP_X_REQUEST_ID='bulk-pg-fail-' + suffix), identifiers, 500)
assert list(User.objects.filter(pk__in=identifiers).order_by('pk').values_list('is_active', flat=True)) == before
assert not OperationLog.objects.filter(request_id='bulk-pg-fail-' + suffix).exists()
print('通过：PostgreSQL 审计已写入后故障同时回滚业务和审计，响应无成功项', flush=True)

scoped = User.objects.create_user('bulk-scope-' + suffix)
role = Role.objects.create(name='批量本人范围-' + suffix)
UserRole.objects.create(user=scoped, role=role)
permission, _ = Permission.objects.get_or_create(code='user:update', defaults={
    'name': '更新用户', 'resource': 'user', 'action': 'update'})
RolePermission.objects.create(role=role, permission=permission)
DataScopeGrant.objects.create(role=role, resource='user', scope='self')
for hidden in [identifiers[0], str(uuid4())]:
    submitted = [str(scoped.pk), hidden]
    verify(client(scoped).post(URL, {'action': 'deactivate', 'user_ids': submitted}, format='json'), submitted, 403)
scoped.refresh_from_db()
assert scoped.is_active and list(User.objects.filter(pk__in=identifiers).order_by('pk').values_list('is_active', flat=True)) == before
print('通过：PostgreSQL 混合范围和不存在对象均整批拒绝且不透露逐项存在性', flush=True)
