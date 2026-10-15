"""仅在 foundation 隔离 PostgreSQL 中验证审计事务和串行快照。"""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from rest_framework.test import APIClient

from apps.logs.models import OperationLog
from apps.permissions.models import Role

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
actor = get_user_model().objects.get(username='admin')
name = 'audit-fixture-' + secrets.token_hex(8)
role = Role.objects.create(name=name)


def client():
    api = APIClient(HTTP_HOST='localhost')
    api.force_authenticate(actor)
    return api


def update(suffix):
    try:
        response = client().patch(f'/api/v1/permissions/roles/{role.pk}/', {'name': name + suffix, 'version': 1},
                                  format='json', HTTP_X_REQUEST_ID='pg-audit-' + suffix)
        return response.status_code
    finally:
        connections.close_all()


with ThreadPoolExecutor(max_workers=2) as pool:
    assert sorted(pool.map(update, ['A', 'B'])) == [200, 409]
rows = list(OperationLog.objects.filter(resource='role', resource_id=str(role.pk)).order_by('created_at'))
assert len(rows) == 1
assert rows[0].before_values['name'] == name
role.refresh_from_db()
assert rows[0].after_values['name'] == role.name and role.version == 2
assert rows[0].request_id in {'pg-audit-A', 'pg-audit-B'}
# An explicit reload may submit the new version; its audit must start at the committed value.
response = client().patch(f'/api/v1/permissions/roles/{role.pk}/',
    {'name': name + 'RELOADED', 'version': role.version}, format='json', HTTP_X_REQUEST_ID='pg-audit-reloaded')
assert response.status_code == 200
rows = list(OperationLog.objects.filter(resource='role', resource_id=str(role.pk)).order_by('created_at'))
assert len(rows) == 2 and rows[1].before_values['name'] == rows[0].after_values['name']
role.refresh_from_db()
assert rows[1].after_values['name'] == role.name and role.version == 3
print('通过：PostgreSQL 并发旧版本一成功一冲突；显式重读后审计快照连续', flush=True)

previous = role.name
with patch('apps.logs.audit.write_audit', side_effect=RuntimeError('isolated audit failure')):
    response = client().patch(f'/api/v1/permissions/roles/{role.pk}/', {'name': name + 'FAIL', 'version': role.version}, format='json')
assert response.status_code == 500
role.refresh_from_db()
assert role.name == previous and role.version == 3 and OperationLog.objects.filter(resource='role', resource_id=str(role.pk)).count() == 2
print('通过：PostgreSQL 审计写入失败回滚角色变更', flush=True)

response = client().get('/api/v1/logs/operation/', {'request_id': rows[0].request_id})
assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
assert response.json()['data']['pagination']['total'] == 1
detail = client().get(f'/api/v1/logs/operation/{rows[0].pk}/')
assert detail.status_code == 200 and detail.json()['before_values']['name'] == name
assert client().delete(f'/api/v1/logs/operation/{rows[0].pk}/').status_code == 405
print('通过：PostgreSQL 关联 ID 精确查询、详情和只读边界', flush=True)
