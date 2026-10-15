"""任务信息含操作者与执行结果，列表、详情和拒绝响应均禁止缓存。"""
import pytest
from rest_framework.test import APIClient

from apps.tasks.models import TaskRecord


@pytest.mark.django_db
def test_task_responses_are_not_cacheable(admin_client, admin_user, member_client):
    record = TaskRecord.objects.create(name='私有任务结果', creator=admin_user, result={'private': True})
    for client, path, status in [
        (admin_client, '/api/v1/tasks/', 200),
        (admin_client, f'/api/v1/tasks/{record.pk}/', 200),
        (member_client, '/api/v1/tasks/', 403),
        (APIClient(), '/api/v1/tasks/', 401),
    ]:
        response = client.get(path)
        assert response.status_code == status
        assert response['Cache-Control'] == 'private, no-store'
