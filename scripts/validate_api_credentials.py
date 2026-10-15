"""Run with manage.py shell in the isolated foundation PostgreSQL project only."""
import sys
import types
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import override_settings
from django.urls import include, path
from django.utils import timezone
from rest_framework.test import APIClient

from apps.api_credentials.models import APICredential
from apps.api_credentials.views import TaskGatewayViewSet
from apps.auth_app.sessions import issue_session
from apps.core.models import DataScopeGrant
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.tasks.models import TaskRecord

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connection.vendor == 'postgresql', '必须使用 PostgreSQL'
base = '/api/v1/api-credentials/'
url_name = 'admincore_api_credential_validation_urls'
urls = types.ModuleType(url_name)
urls.urlpatterns = [path('api/v1/api-credentials/', include('apps.api_credentials.urls')),
                    path('api/v1/auth/', include('apps.auth_app.urls')),
                    path('api/v1/tasks/', include('apps.tasks.urls'))]
assert url_name not in sys.modules
sys.modules[url_name] = urls
suffix = uuid4().hex[:12]
username = 'api_credential_' + suffix
try:
    with override_settings(ROOT_URLCONF=url_name, ADMINCORE_MODULES=tuple(dict.fromkeys((*settings.ADMINCORE_MODULES, 'api_credentials', 'tasks')))):
        with transaction.atomic():
            owner = get_user_model().objects.create_user(username, password=uuid4().hex)
            # Test-only fixture password is never emitted or persisted outside the SQL rollback.
            confirmation = uuid4().hex
            owner.set_password(confirmation); owner.save(update_fields=['password'])
            role = Role.objects.create(name='api-credential-' + suffix)
            UserRole.objects.create(user=owner, role=role)
            for code in ('api_credential:read', 'api_credential:create', 'api_credential:revoke', 'task:read'):
                resource, action = code.split(':')
                permission, _ = Permission.objects.get_or_create(code=code,
                    defaults={'name': code, 'resource': resource, 'action': action})
                RolePermission.objects.create(role=role, permission=permission)
            DataScopeGrant.objects.create(role=role, resource='task', scope='self')
            own = TaskRecord.objects.create(creator=owner, name='Open API own task', result={'private': 'not public'})
            TaskRecord.objects.create(name='Open API outside scope')
            manager = APIClient(HTTP_HOST='localhost')
            manager.credentials(HTTP_AUTHORIZATION='Bearer ' + str(issue_session(owner).access_token))
            response = manager.post(base + 'credentials/', {'name': 'PG validation', 'scopes': ['task:read'],
                'expires_at': (timezone.now() + timedelta(days=1)).isoformat(), 'current_password': confirmation}, format='json')
            assert response.status_code == 201
            token = response.json()['data']['token']
            credential_id = response.json()['data']['id']
            assert token not in repr(APICredential.objects.get(pk=credential_id).__dict__)
            assert 'token' not in manager.get(base + 'credentials/').json()['data']['items'][0]
            print('通过：真实 PostgreSQL 独立凭证仅签发响应展示密钥，列表和存储无明文', flush=True)

            client = APIClient(HTTP_HOST='localhost', HTTP_AUTHORIZATION='ApiToken ' + token)
            response = client.get(base + 'tasks/?ordering=-created_at')
            assert response.status_code == 200
            assert [row['id'] for row in response.json()['data']['items']] == [str(own.pk)]
            assert 'result' not in response.json()['data']['items'][0]
            assert client.get('/api/v1/tasks/').status_code == 401
            assert client.get(base + 'credentials/').status_code == 401
            assert client.post(base + 'tasks/', {}, format='json').status_code == 403
            assert client.get(base + 'tasks/?ordering=password').status_code == 400
            print('通过：真实 PostgreSQL 只读网关保留本人范围和查询契约，不进入 JWT/写入/账号管理链', flush=True)

            def slow_query(self):
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_sleep(0.2)')
                return TaskRecord.objects.all()
            with override_settings(ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS=50):
                with patch.object(TaskGatewayViewSet, 'get_queryset', slow_query):
                    assert client.get(base + 'tasks/').status_code == 503
            assert client.get(base + 'tasks/').status_code == 200
            assert OperationLog.objects.filter(resource='api_credential', resource_id=credential_id).count() == 2
            print('通过：真实 PostgreSQL 开放网关 SQL 超时503后连接恢复，重复读取不膨胀审计行', flush=True)

            RolePermission.objects.filter(role=role, permission__code='task:read').delete()
            assert client.get(base + 'tasks/').status_code == 403
            response = manager.post(base + f'credentials/{credential_id}/revoke/', {'current_password': confirmation}, format='json')
            assert response.status_code == 200
            assert client.get(base + 'tasks/').status_code == 401
            print('通过：真实 PostgreSQL 实时撤权和密码确认撤销立即生效', flush=True)
            transaction.set_rollback(True)
    assert not get_user_model().objects.filter(username=username).exists()
    print('通过：本段开放凭证验收数据已整体回滚', flush=True)
finally:
    sys.modules.pop(url_name, None)
