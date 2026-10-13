"""幂等请求和可靠事件的最小可执行契约。"""
from datetime import timedelta

import pytest
from django.utils import timezone
from django.db import transaction
from unittest.mock import patch

from apps.core.events import enqueue_event
from apps.core.models import IdempotencyRecord, OutboxEvent
from apps.core.tasks import dispatch_outbox, cleanup_expired_idempotency
from apps.logs.models import OperationLog
from apps.notifications.models import Notification
from apps.approvals.models import ApprovalRequest

pytestmark = pytest.mark.django_db


def approval_payload(admin_user, title='同一申请'):
    return {'title': title, 'request_type': 'other', 'content': '一次提交', 'assignee_id': str(admin_user.pk)}


def test_same_idempotency_key_replays_without_duplicate(member_client, admin_user):
    payload = approval_payload(admin_user)
    first = member_client.post('/api/v1/approvals/', payload, format='json', HTTP_IDEMPOTENCY_KEY='approval-1')
    second = member_client.post('/api/v1/approvals/', payload, format='json', HTTP_IDEMPOTENCY_KEY='approval-1')
    assert first.status_code == second.status_code == 201
    assert first.json()['data']['id'] == second.json()['data']['id']
    assert second['Idempotency-Replayed'] == 'true'
    assert ApprovalRequest.objects.count() == 1
    assert IdempotencyRecord.objects.filter(status='succeeded').count() == 1


def test_same_key_different_payload_is_rejected(member_client, admin_user):
    first = member_client.post('/api/v1/approvals/', approval_payload(admin_user), format='json', HTTP_IDEMPOTENCY_KEY='approval-2')
    changed = member_client.post('/api/v1/approvals/', approval_payload(admin_user, '另一申请'), format='json', HTTP_IDEMPOTENCY_KEY='approval-2')
    assert first.status_code == 201
    assert changed.status_code == 409
    assert ApprovalRequest.objects.count() == 1


def test_failed_business_request_does_not_leave_idempotency_record(member_client, admin_user):
    response = member_client.post('/api/v1/approvals/', {'title': '缺审批人'}, format='json', HTTP_IDEMPOTENCY_KEY='invalid-1')
    assert response.status_code == 400
    assert not IdempotencyRecord.objects.filter(key='invalid-1').exists()


def test_outbox_retries_and_consumes_once(member_user):
    event = enqueue_event('notification.created', 'event-retry-1', {
        'recipient_ids': ['missing-user'], 'title': '待重试', 'content': '',
        'notification_type': 'system', 'link': '', 'data': None,
    })
    dispatch_outbox()
    event.refresh_from_db()
    assert event.status == 'failed' and event.attempts == 1
    event.payload['recipient_ids'] = [str(member_user.pk)]
    event.available_at = timezone.now() - timedelta(seconds=1)
    event.save(update_fields=['payload', 'available_at', 'updated_at'])
    dispatch_outbox()
    event.refresh_from_db()
    assert event.status == 'succeeded'
    assert Notification.objects.filter(title='待重试').count() == 1
    dispatch_outbox()
    assert Notification.objects.filter(title='待重试').count() == 1


def test_transaction_rollback_discards_event_and_dispatch(django_capture_on_commit_callbacks):
    with patch('apps.core.tasks.dispatch_outbox.delay') as delay:
        with django_capture_on_commit_callbacks(execute=True):
            with pytest.raises(RuntimeError), transaction.atomic():
                enqueue_event('notification.created', 'rolled-back', {'recipient_ids': []})
                raise RuntimeError('业务失败')
        assert not OutboxEvent.objects.filter(event_key='rolled-back').exists()
        delay.assert_not_called()


def test_broker_failure_keeps_event_for_compensation(member_user, django_capture_on_commit_callbacks):
    with patch('apps.core.tasks.dispatch_outbox.delay', side_effect=ConnectionError('secret-broker-url')):
        with django_capture_on_commit_callbacks(execute=True):
            event = enqueue_event('notification.created', 'broker-down', {
                'recipient_ids': [str(member_user.pk)], 'title': '补偿通知',
            })
    assert event.status == 'pending'
    assert dispatch_outbox() == {'processed': 1, 'failed': 0}
    assert Notification.objects.filter(title='补偿通知').count() == 1


def test_event_key_cannot_represent_different_payload():
    enqueue_event('notification.created', 'unique-event', {'title': '原始'})
    with pytest.raises(ValueError):
        enqueue_event('notification.created', 'unique-event', {'title': '修改'})
    assert OutboxEvent.objects.get(event_key='unique-event').payload == {'title': '原始'}


def test_reliable_event_admin_diagnostics_and_retry(admin_client, member_client, member_user, django_capture_on_commit_callbacks):
    event = enqueue_event('notification.created', 'admin-retry', {
        'recipient_ids': [str(member_user.pk)], 'title': '管理员重试', 'content': '不得回显的业务正文',
    })
    event.status = 'failed'
    event.save(update_fields=['status'])
    url = f'/api/v1/reliability/events/{event.pk}/'
    assert member_client.get(url).status_code == 403
    assert member_client.post(url + 'retry/').status_code == 403
    detail = admin_client.get(url)
    assert detail.status_code == 200 and detail.json()['data']['status'] == 'failed'
    assert 'payload' not in detail.json()['data']
    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(url + 'retry/')
    assert response.status_code == 200
    event.refresh_from_db()
    assert event.status == 'succeeded'
    assert OperationLog.objects.filter(resource='outbox_event', resource_id=str(event.pk)).count() == 1
    assert admin_client.post(url + 'retry/').status_code == 409


def test_replay_requires_current_approval_assignee(member_client, admin_client, admin_user, member_user):
    created = member_client.post('/api/v1/approvals/', approval_payload(admin_user), format='json')
    item_id = created.json()['data']['id']
    url = f'/api/v1/approvals/{item_id}/approve/'
    first = admin_client.post(url, {'comment': ''}, format='json', HTTP_IDEMPOTENCY_KEY='decision')
    assert first.status_code == 200
    assert admin_client.post(url, {'comment': ''}, format='json', HTTP_IDEMPOTENCY_KEY='decision')['Idempotency-Replayed'] == 'true'
    ApprovalRequest.objects.filter(pk=item_id).update(assignee=member_user)
    assert admin_client.post(url, {'comment': ''}, format='json', HTTP_IDEMPOTENCY_KEY='decision').status_code == 404


def test_event_menu_visible_only_to_admin_and_operator_removal_preserved(admin_client, admin_user, member_client, monkeypatch):
    from django.core.management import call_command
    from apps.permissions.models import Menu
    from io import StringIO
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'PrivateReview#87392')
    admin_user.set_password('PrivateReview#87392')
    admin_user.save(update_fields=['password'])
    tokens = admin_client.post('/api/v1/auth/login/', {'username': admin_user.username, 'password': 'PrivateReview#87392'}, format='json').json()
    admin_client.credentials(HTTP_AUTHORIZATION='Bearer ' + tokens['access'])
    call_command('bootstrap_admincore', stdout=StringIO())
    menu = Menu.objects.get(path='/reliability/events')
    assert str(menu.pk) in {item['id'] for item in admin_client.get('/api/v1/permissions/menus/my_menu/').json()['data']}
    assert str(menu.pk) not in {item['id'] for item in member_client.get('/api/v1/permissions/menus/my_menu/').json()['data']}
    menu.delete()
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not Menu.objects.filter(path='/reliability/events').exists()


def test_notification_replay_requires_current_admin_permission(admin_client, admin_user, member_user):
    payload = {'recipient_ids': [str(member_user.pk)], 'title': '权限重放'}
    first = admin_client.post('/api/v1/notifications/', payload, format='json', HTTP_IDEMPOTENCY_KEY='send')
    assert first.status_code == 201
    admin_user.is_staff = admin_user.is_superuser = False
    admin_user.save(update_fields=['is_staff', 'is_superuser'])
    assert admin_client.post('/api/v1/notifications/', payload, format='json', HTTP_IDEMPOTENCY_KEY='send').status_code == 403
    assert Notification.objects.filter(title='权限重放').count() == 1


@pytest.mark.parametrize('key', ['', 'has space', 'x' * 129, '中文'])
def test_invalid_idempotency_key_rejected(member_client, admin_user, key):
    response = member_client.post('/api/v1/approvals/', approval_payload(admin_user), format='json', HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 400
    assert not ApprovalRequest.objects.exists()


def test_expired_key_can_start_new_operation_then_cleanup(member_client, admin_user):
    payload = approval_payload(admin_user)
    first = member_client.post('/api/v1/approvals/', payload, format='json', HTTP_IDEMPOTENCY_KEY='expired')
    IdempotencyRecord.objects.filter(key='expired').update(expires_at=timezone.now() - timedelta(seconds=1))
    second = member_client.post('/api/v1/approvals/', payload, format='json', HTTP_IDEMPOTENCY_KEY='expired')
    assert first.status_code == second.status_code == 201
    assert first.json()['data']['id'] != second.json()['data']['id']
    IdempotencyRecord.objects.filter(key='expired').update(expires_at=timezone.now() - timedelta(seconds=1))
    assert cleanup_expired_idempotency()['deleted_records'] == 1


def test_disabled_channel_keeps_failed_event_until_reenabled(member_user, settings):
    event = enqueue_event('notification.created', 'disabled-channel', {
        'recipient_ids': [str(member_user.pk)], 'title': '恢复渠道',
    })
    modules = settings.ADMINCORE_MODULES
    settings.ADMINCORE_MODULES = tuple(item for item in modules if item != 'notifications')
    assert dispatch_outbox() == {'processed': 0, 'failed': 1}
    event.refresh_from_db()
    assert event.last_error == 'notifications_disabled'
    assert not Notification.objects.exists()
    settings.ADMINCORE_MODULES = modules
    event.available_at = timezone.now() - timedelta(seconds=1)
    event.save(update_fields=['available_at'])
    assert dispatch_outbox() == {'processed': 1, 'failed': 0}
    dispatch_outbox()
    assert Notification.objects.filter(title='恢复渠道').count() == 1
