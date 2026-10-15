"""仅 PostgreSQL 锁不可用映射为可恢复冲突，其余数据库故障不得冒充忙锁。"""
from unittest.mock import patch
import pytest
from django.db import OperationalError, connection
from django.utils import timezone

from apps.core.models import OutboxEvent
from apps.logs.models import OperationLog

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('sqlstate,expected', [('55P03', 409), ('40P01', 500), ('08006', 500)])
def test_retry_busy_mapping_preserves_event_and_audit(admin_client, sqlstate, expected):
    row = OutboxEvent.objects.create(topic='notification.created', event_key='retry-lock-' + sqlstate,
                                    payload={}, status='failed', available_at=timezone.now())
    failure = OperationalError('database details must not reach client')
    cause = Exception('driver error')
    cause.sqlstate = sqlstate
    failure.__cause__ = cause
    admin_client.raise_request_exception = False
    from django.db.models.query import QuerySet
    original = QuerySet.get

    def fail_event_get(queryset, *args, **kwargs):
        if queryset.model is OutboxEvent:
            assert connection.in_atomic_block and queryset.query.select_for_update_nowait
            raise failure
        return original(queryset, *args, **kwargs)

    with patch.object(QuerySet, 'get', fail_event_get):
        response = admin_client.post(f'/api/v1/reliability/events/{row.pk}/retry/')
    assert response.status_code == expected
    assert 'database details' not in response.content.decode()
    if expected == 409:
        assert response.json()['message'] == '事件正在处理，请稍后重试'
    row.refresh_from_db()
    assert row.status == 'failed' and row.attempts == 0
    assert not OperationLog.objects.filter(resource='outbox_event', resource_id=str(row.pk)).exists()


def test_retry_uses_nowait_and_succeeds_when_uncontended(admin_client):
    row = OutboxEvent.objects.create(topic='notification.created', event_key='retry-uncontended',
                                    payload={}, status='failed', available_at=timezone.now())
    from django.db.models.query import QuerySet
    original = QuerySet.select_for_update
    observed = []

    def check(queryset, *args, **kwargs):
        if queryset.model is OutboxEvent:
            observed.append(kwargs)
        return original(queryset, *args, **kwargs)

    with patch.object(QuerySet, 'select_for_update', check):
        response = admin_client.post(f'/api/v1/reliability/events/{row.pk}/retry/')
    assert response.status_code == 200 and observed == [{'nowait': True}]
    row.refresh_from_db()
    assert row.status == 'pending'
    assert OperationLog.objects.filter(resource='outbox_event', resource_id=str(row.pk)).count() == 1
