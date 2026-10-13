"""固定查询上限而非机器相关耗时，防止分页列表重新出现 N+1。"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from apps.logs.models import OperationLog, ExceptionLog
from apps.tasks.models import TaskRecord
from apps.files.models import FileModel
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

@pytest.mark.parametrize('path,model', [
    ('/api/v1/logs/operation/', OperationLog),
    ('/api/v1/logs/exception/', ExceptionLog),
    ('/api/v1/tasks/', TaskRecord),
    ('/api/v1/files/', FileModel),
    ('/api/v1/users/', get_user_model()),
])
def test_paginated_list_query_count_does_not_grow_with_rows(admin_user, path, model):
    if model is OperationLog:
        model.objects.bulk_create([model(user=admin_user, action='read', resource='fixture', ip_address='127.0.0.1') for _ in range(50)])
    elif model is ExceptionLog:
        model.objects.bulk_create([model(user=admin_user, level='error', message='fixture') for _ in range(50)])
    elif model is TaskRecord:
        model.objects.bulk_create([model(creator=admin_user, name='fixture') for _ in range(50)])
    elif model is FileModel:
        model.objects.bulk_create([model(uploader=admin_user, original_name='fixture.txt', file_type='txt') for _ in range(50)])
    else:
        model.objects.bulk_create([model(username=f'fixture_{i}', password='!') for i in range(50)])
    client = APIClient()
    client.force_authenticate(admin_user)
    with CaptureQueriesContext(connection) as queries:
        response = client.get(path, {'page_size': 100})
    assert response.status_code == 200
    assert len(response.json()['data']['items']) >= 50
    assert len(queries) <= 3, [query['sql'] for query in queries]
