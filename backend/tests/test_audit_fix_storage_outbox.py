"""删除意图及外部派发的提交、补偿、领取和未知结果边界。"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from apps.core.models import OutboxEvent
from apps.core.tasks import dispatch_outbox
from apps.files.models import FileModel
from tests.test_recycle import file_for


@pytest.mark.django_db
def test_delete_outer_rollback_preserves_both_record_and_object(admin_user):
    row = file_for(admin_user)
    key = row.file.name
    with pytest.raises(RuntimeError), transaction.atomic():
        row.hard_delete()
        raise RuntimeError('commit_or_audit_failure')
    assert FileModel.objects.filter(pk=row.pk).exists()
    assert row.file.storage.exists(key)
    assert not OutboxEvent.objects.filter(topic='file.purge').exists()


@pytest.mark.django_db
def test_durable_delete_survives_storage_failure_and_retry(admin_user):
    row = file_for(admin_user)
    key = row.file.name
    row.hard_delete()
    assert not FileModel.objects.filter(pk=row.pk).exists()
    event = OutboxEvent.objects.get(topic='file.purge')
    assert row.file.storage.exists(key)
    with patch.object(row.file.storage, 'delete', side_effect=OSError('private-storage-url')):
        assert dispatch_outbox()['failed'] == 1
    event.refresh_from_db()
    assert event.status == 'failed' and 'private-storage-url' not in event.last_error
    assert row.file.storage.exists(key)
    OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now())
    assert dispatch_outbox()['processed'] == 1
    assert not row.file.storage.exists(key)
    assert dispatch_outbox()['processed'] == 0


@pytest.mark.django_db
def test_expired_storage_claim_can_replay_idempotently(admin_user):
    row = file_for(admin_user)
    row.hard_delete()
    row.file.storage.delete(row.file.name)  # 对象已删，领取 worker 未写回即退出。
    OutboxEvent.objects.filter(topic='file.purge').update(status='processing', attempts=1,
        available_at=timezone.now() - timedelta(seconds=1))
    assert dispatch_outbox()['processed'] == 1


@pytest.mark.django_db
def test_storage_change_blocks_cleanup(admin_user):
    row = file_for(admin_user)
    row.hard_delete()
    with patch('apps.files.deletion.storage_identity', return_value='different-target'):
        assert dispatch_outbox()['failed'] == 1
    assert row.file.storage.exists(row.file.name)


@pytest.mark.django_db
def test_external_claim_commits_before_dispatch_and_fences_expiry():
    event = OutboxEvent.objects.create(topic='task.failed', event_key='claim-test', payload={}, available_at=timezone.now())
    def send(payload):
        event.refresh_from_db()
        assert event.status == 'processing' and event.attempts == 1
        # 已领取的并发 dispatcher 不会重复发送。
        assert dispatch_outbox() == {'processed': 0, 'failed': 0}
        OutboxEvent.objects.filter(pk=event.pk).update(status='failed', last_error='dispatch_exhausted')
    with patch('apps.tasks.reliability.deliver_failure', side_effect=send) as channel:
        assert dispatch_outbox() == {'processed': 0, 'failed': 0}
        channel.assert_called_once()
    event.refresh_from_db()
    assert event.status == 'failed' and event.last_error == 'dispatch_exhausted'


@pytest.mark.django_db
def test_exhausted_external_event_cannot_starve_the_next_batch():
    event = OutboxEvent.objects.create(topic='auth.email', event_key='exhausted-first', payload={},
        status='failed', attempts=5, available_at=timezone.now() - timedelta(days=1))
    OutboxEvent.objects.create(topic='auth.email', event_key='next-message', payload={}, available_at=timezone.now())
    with patch('apps.auth_app.recovery.deliver_challenge') as send:
        assert dispatch_outbox(limit=1) == {'processed': 0, 'failed': 0}
        send.assert_not_called()
        event.refresh_from_db()
        assert event.last_error == 'dispatch_exhausted'
        assert dispatch_outbox(limit=1) == {'processed': 1, 'failed': 0}
        send.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize('state', ['processing', 'failed'])
def test_interrupted_delivery_never_replays_unknown_send(admin_client, member_user, state):
    from tests.test_message_templates import template, send
    from apps.notifications.models import MessageDelivery
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user).status_code == 202
    row = MessageDelivery.objects.get()
    MessageDelivery.objects.filter(pk=row.pk).update(status='sending', attempts=1)
    event = OutboxEvent.objects.get(topic='notification.delivery')
    OutboxEvent.objects.filter(pk=event.pk).update(status=state, attempts=1, available_at=timezone.now())
    with patch.dict('apps.notifications.message_channels.CHANNELS', {'inapp': lambda *_: pytest.fail('unknown send replayed')}):
        assert dispatch_outbox()['failed'] == 1
    row.refresh_from_db()
    event.refresh_from_db()
    assert row.status == 'terminated' and row.last_error == 'delivery_outcome_unknown'
    assert event.last_error == 'dispatch_exhausted'
    assert dispatch_outbox() == {'processed': 0, 'failed': 0}


@pytest.mark.django_db
def test_interrupted_event_reconciles_known_delivery_result(admin_client, member_user):
    from tests.test_message_templates import template, send
    from apps.notifications.models import MessageDelivery
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user).status_code == 202
    MessageDelivery.objects.update(status='succeeded', attempts=1, sent_at=timezone.now())
    OutboxEvent.objects.filter(topic='notification.delivery').update(status='processing', attempts=1, available_at=timezone.now())
    with patch('apps.notifications.message_services.deliver', side_effect=AssertionError('replayed')):
        assert dispatch_outbox()['processed'] == 1
    assert OutboxEvent.objects.get(topic='notification.delivery').status == 'succeeded'


@pytest.mark.django_db
@pytest.mark.parametrize('payload', [{}, [], {'delivery_id': 'invalid'}])
def test_malformed_delivery_intent_is_contained(payload):
    OutboxEvent.objects.create(topic='notification.delivery', event_key='malformed', payload=payload, available_at=timezone.now())
    assert dispatch_outbox()['failed'] == 1
    assert OutboxEvent.objects.get().last_error == 'dispatch_exhausted'


@pytest.mark.django_db(transaction=True)
def test_network_dispatch_does_not_hold_postgres_user_locks(admin_user):
    """真实 PostgreSQL 第二连接更新；SQLite 不提供此行锁语义。"""
    from django.db import connection
    if connection.vendor != 'postgresql':
        pytest.skip('由 scripts/validate_audit_fixes.py 在独立 PostgreSQL 中执行')
    import psycopg2
    admin_user.verified_email = admin_user.email
    admin_user.save(update_fields=['verified_email'])
    from apps.notifications.models import MessageTemplate, MessageTemplateVersion, MessageDelivery
    from apps.tasks.models import TaskRecord
    template = MessageTemplate.objects.create(code='audit-lock', name='锁回归')
    version = MessageTemplateVersion.objects.create(template=template, number=1, subject='Synthetic', body='Synthetic', creator=admin_user)
    row = MessageDelivery.objects.create(version=version, recipient=admin_user, creator=admin_user, channel='inapp',
        subject='Synthetic', body='Synthetic', actor_session_version=admin_user.session_version,
        expires_at=timezone.now() + timedelta(hours=1))
    OutboxEvent.objects.create(topic='notification.delivery', event_key='audit-lock', payload={'delivery_id': str(row.pk)}, available_at=timezone.now())
    checked = []
    def network(*args, **kwargs):
        assert not connection.in_atomic_block
        config = connection.settings_dict
        with psycopg2.connect(dbname=config['NAME'], user=config['USER'], password=config['PASSWORD'],
                             host=config['HOST'], port=config['PORT']) as other:
            with other.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='150ms'")
                cursor.execute('UPDATE auth_app_user SET login_count=login_count WHERE id=%s', [str(admin_user.pk)])
        checked.append(True)
        return 1
    with patch.dict('apps.notifications.message_channels.CHANNELS', {'inapp': network}):
        assert dispatch_outbox()['processed'] == 1
    record = TaskRecord.objects.create(name='Synthetic', task_type='import', status='failed', creator=admin_user)
    OutboxEvent.objects.create(topic='task.failed', event_key='audit-email-lock', payload={'record_id': str(record.pk)}, available_at=timezone.now())
    with patch('apps.tasks.reliability.config_value', return_value=True), patch('apps.notifications.message_channels.enabled', return_value=True), patch('django.core.mail.EmailMessage.send', side_effect=network):
        assert dispatch_outbox()['processed'] == 1
    assert len(checked) == 2
