"""仅在 foundation 隔离 PostgreSQL 验证查询边界与真实同值分页。"""
from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import DataScopeGrant
from apps.notifications.models import Notification
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.users.views import UserViewSet

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connection.vendor == 'postgresql', '必须使用 PostgreSQL'
User = get_user_model()
admin = User.objects.get(username='admin')
client = APIClient(HTTP_HOST='localhost')
client.force_authenticate(admin)

# 整个验收只回滚本段自建数据，不清理其他阶段的夹具。
with transaction.atomic():
    ids = [UUID(int=value) for value in [9, 3, 7, 1, 5]]
    assert not User.objects.filter(pk__in=ids).exists()
    User.objects.bulk_create([User(id=identifier, username=f'query_tie_{identifier.int}',
        password='!', login_count=7) for identifier in ids])
    User.objects.filter(pk__in=ids).update(created_at=timezone.now())
    expected = [str(identifier) for identifier in sorted(ids)]
    for ordering in [None, '-login_count']:
        result = []
        for page in [1, 2, 3]:
            params = {'search': 'query_tie_', 'page_size': 2, 'page': page}
            if ordering:
                params['ordering'] = ordering
            response = client.get('/api/v1/users/', params)
            assert response.status_code == 200
            result.extend(row['id'] for row in response.json()['data']['items'])
        assert result == expected
    print('通过：真实 PostgreSQL 默认/指定同值排序按主键补齐，跨页无重复遗漏', flush=True)

    invalid = ['unknown=1', 'search=a&search=b', 'search=%00', 'ordering=password',
        'ordering=username,-username', 'ordering=username,password', 'search=' + 'a' * 201]
    with patch.object(UserViewSet, 'get_queryset', side_effect=AssertionError('无效输入不应查询资源')):
        for query in invalid:
            assert client.get('/api/v1/users/?' + query).status_code == 400
    assert client.get('/api/v1/users/', {'search': '中' * 200}).status_code == 200
    print('通过：真实 PostgreSQL 无效/重复/越界输入与敏感排序在资源查询前拒绝', flush=True)

    member = User.objects.create(username='query_scope_member', password='!')
    role = Role.objects.create(name='query-scope-fixture')
    UserRole.objects.create(user=member, role=role)
    permission = Permission.objects.get(code='user:read')
    RolePermission.objects.create(role=role, permission=permission)
    DataScopeGrant.objects.create(role=role, resource='user', scope='self')
    scoped = APIClient(HTTP_HOST='localhost')
    scoped.force_authenticate(member)
    response = scoped.get('/api/v1/users/?ordering=login_count')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['data']['items']] == [str(member.pk)]
    mine = Notification.objects.create(recipient=member, title='query own')
    Notification.objects.create(recipient=admin, title='query outside')
    response = scoped.get('/api/v1/notifications/?scope=all&search=query&ordering=created_at')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['data']['items']] == [str(mine.pk)]
    RolePermission.objects.filter(role=role).delete()
    assert scoped.get('/api/v1/users/?ordering=login_count').status_code == 403
    print('通过：真实 PostgreSQL 排序保留数据范围、scope=all不越权且撤权立即生效', flush=True)
    transaction.set_rollback(True)
assert not User.objects.filter(username__startswith='query_').exists()
print('通过：本段查询夹具事务已回滚', flush=True)
