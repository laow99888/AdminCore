"""foundation 隔离 PostgreSQL 中运行真实 Django admin 表单和 action。"""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client

from apps.logs.models import OperationLog
from apps.permissions.models import Role

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql', '必须使用 PostgreSQL'
actor = get_user_model().objects.get(username='admin')
prefix = 'admin-audit-pg-' + secrets.token_hex(8)
role = Role.objects.create(name=prefix)


def browser():
    result = Client(HTTP_HOST='backend')
    result.force_login(actor)
    return result


def form(name, version=1):
    return {'name': name, 'edit_version': str(version), 'description': '', 'is_active': 'on', '_save': '保存',
            'permissions-TOTAL_FORMS': '0', 'permissions-INITIAL_FORMS': '0',
            'permissions-MIN_NUM_FORMS': '0', 'permissions-MAX_NUM_FORMS': '1000'}


def update(suffix):
    try:
        response = browser().post(f'/admin/permissions/role/{role.pk}/change/', form(prefix + suffix),
                                  HTTP_X_REQUEST_ID=prefix + suffix)
        assert response.status_code in (200, 302)
        return response.status_code, suffix
    finally:
        connections.close_all()


with ThreadPoolExecutor(max_workers=2) as pool:
    outcomes = list(pool.map(update, ['A', 'B']))
assert sorted(status for status, _ in outcomes) == [200, 302]
role.refresh_from_db()
assert role.version == 2
assert OperationLog.objects.filter(resource='role', resource_id=str(role.pk)).count() == 1
stale_suffix = next(suffix for status, suffix in outcomes if status == 200)
response = browser().post(f'/admin/permissions/role/{role.pk}/change/',
                          form(prefix + stale_suffix, version=2),
                          HTTP_X_REQUEST_ID=prefix + '-retry')
assert response.status_code == 302
rows = list(OperationLog.objects.filter(resource='role', resource_id=str(role.pk)).order_by('created_at'))
assert len(rows) == 2
assert rows[0].before_values['name'] == prefix
assert rows[1].before_values['name'] == rows[0].after_values['name']
role.refresh_from_db()
assert role.version == 3
assert rows[1].after_values['name'] == role.name
print('通过：PostgreSQL Django admin 并发版本冲突阻止覆盖，重载后修改前值链连续', flush=True)

other = Role.objects.create(name=prefix + 'other')
ids = [role.pk, other.pk]
request = browser()
before_count = OperationLog.objects.count()
payload = {'action': 'delete_selected', 'post': 'yes', '_selected_action': ids}
with patch('apps.logs.admin_audit.write_audit', side_effect=RuntimeError('isolated failure')):
    response = request.post('/admin/permissions/role/', payload)
assert response.status_code == 500 and Role.objects.filter(pk__in=ids).count() == 2
assert OperationLog.objects.count() == before_count
response = request.post('/admin/permissions/role/', payload, HTTP_X_REQUEST_ID=prefix + '-bulk')
assert response.status_code == 302 and not Role.objects.filter(pk__in=ids).exists()
results = OperationLog.objects.get(request_id=prefix + '-bulk', resource_id='').batch_results
assert sorted(result['id'] for result in results) == sorted(str(pk) for pk in ids)
print('通过：PostgreSQL Django admin 批量删除审计事务、逐项结果与失败回滚', flush=True)
