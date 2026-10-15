"""入口接线与 SQLite 兼容；真实取消/锁竞争由隔离 PostgreSQL 脚本验证。"""
from contextlib import contextmanager
from unittest.mock import patch
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.exceptions import APIError
from apps.core.query_budget import query_budget


@pytest.mark.parametrize('name,value,accepted', [
    ('ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS', '0', False),
    ('ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS', '300001', False),
    ('ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS', 'invalid', False),
    ('ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS', '300000', True),
    ('ADMINCORE_QUERY_LOCK_TIMEOUT_MS', '-1', False),
    ('ADMINCORE_QUERY_LOCK_TIMEOUT_MS', '30001', False),
    ('ADMINCORE_QUERY_LOCK_TIMEOUT_MS', '', False),
    ('ADMINCORE_QUERY_LOCK_TIMEOUT_MS', '1', True),
])
def test_budget_configuration_rejects_disabled_unbounded_and_invalid_values(name, value, accepted):
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', 'import config.settings.base'],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, name: value},
        capture_output=True, text=True, encoding='utf-8')
    assert (result.returncode == 0) is accepted
    if not accepted:
        assert 'ImproperlyConfigured' in result.stderr and name in result.stderr


def test_sqlite_budget_does_not_add_queries_or_transactions(db):
    assert connection.vendor == 'sqlite'
    with CaptureQueriesContext(connection) as queries:
        with query_budget():
            pass
    assert len(queries) == 0


def test_budget_schema_preserves_paginated_success_and_adds_503():
    from drf_spectacular.generators import SchemaGenerator
    schema = SchemaGenerator().get_schema(request=None, public=True)
    for path in ['/api/v1/users/', '/api/v1/files/', '/api/v1/tasks/', '/api/v1/logs/operation/']:
        responses = schema['paths'][path]['get']['responses']
        assert set(responses) >= {'200', '503'}
        assert 'Paginated' in responses['200']['content']['application/json']['schema']['$ref']
        assert responses['503']['content']['application/json']['schema']['$ref'].endswith('/MessageResponse')
    responses = schema['paths']['/api/v1/data-io/export/']['get']['responses']
    assert set(responses) >= {'200', '503'}
    assert responses['200']['content']['text/csv']['schema'] == {'type': 'string', 'format': 'binary'}


@pytest.mark.parametrize('path,target', [
    ('users/', 'apps.core.query_budget.query_budget'),
    ('files/', 'apps.core.query_budget.query_budget'),
    ('tasks/', 'apps.core.query_budget.query_budget'),
    ('logs/operation/', 'apps.core.query_budget.query_budget'),
    ('permissions/roles/', 'apps.core.query_budget.query_budget'),
    ('data-io/export/?resource=users&export_format=csv', 'apps.data_io.views.query_budget'),
])
def test_list_and_export_expose_safe_localized_timeout(admin_client, path, target):
    @contextmanager
    def expired(*args, **kwargs):
        raise APIError('查询超时或等待锁过久，请缩小筛选范围后重试', status_code=503)
        yield  # pragma: no cover

    # 导出装饰器在定义时绑定；替换其上下文重建入口，不更改视图逻辑。
    if target == 'apps.data_io.views.query_budget':
        from apps.data_io.views import DataExportView
        replacement = expired()(DataExportView.get.__wrapped__)
        mocked = patch.object(DataExportView, 'get', replacement)
    else:
        mocked = patch(target, expired)
    with mocked:
        response = admin_client.get('/api/v1/' + path, HTTP_ACCEPT_LANGUAGE='en')
    assert response.status_code == 503
    assert response.json() == {'code': 503, 'message':
        'The query timed out or waited too long for a lock. Narrow your filters and try again.', 'data': None}
