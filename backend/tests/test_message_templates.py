from datetime import timedelta
from unittest.mock import patch
import pytest
from django.test import override_settings
from django.utils import timezone
from django.core import mail

from apps.core.models import OutboxEvent
from apps.core.tasks import dispatch_outbox
from apps.logs.models import OperationLog
from apps.notifications.models import MessageTemplate, MessageTemplateVersion, MessageDelivery, Notification

pytestmark = pytest.mark.django_db
BASE = '/api/v1/notifications/templates/'
DELIVERIES = '/api/v1/notifications/deliveries/'


def template(client, **extra):
    return client.post(BASE, {'code': 'fixture', 'name': 'Fixture', 'revision': 0, 'enabled': True,
        'subject': 'Hello ${name}', 'body': 'Text ${name}', 'variables': ['name'], **extra}, format='json')


def send(client, identifier, user, **extra):
    return client.post(BASE + identifier + '/send/', {'revision': 1, 'recipient_ids': [str(user.pk)],
        'channels': ['inapp'], 'values': {'name': 'private fixture'}, **extra}, format='json', HTTP_IDEMPOTENCY_KEY='message-fixture')


def test_create_edit_versions_preview_and_no_secret_audit(admin_client):
    response = template(admin_client)
    assert response.status_code == 201
    identifier = response.json()['data']['id']
    assert response['Cache-Control'] == 'private, no-store'
    response = admin_client.post(BASE + identifier + '/preview/', {'revision': 1, 'values': {'name': '<script>fixture</script>'}}, format='json')
    assert response.status_code == 200 and response.json()['data']['subject'] == 'Hello <script>fixture</script>'
    response = admin_client.patch(BASE + identifier + '/', {'code': 'fixture', 'name': 'Changed', 'revision': 1,
        'enabled': True, 'subject': 'New ${name}', 'body': 'Private content ${name}', 'variables': ['name']}, format='json')
    assert response.status_code == 200 and response.json()['data']['revision'] == 2
    assert list(MessageTemplateVersion.objects.values_list('number', flat=True)) == [2, 1]
    logs = OperationLog.objects.filter(resource='message_template')
    assert 'Private content' not in str(list(logs.values())) and 'Text ${name}' not in str(list(logs.values()))
    assert admin_client.patch(BASE + identifier + '/', {'code': 'fixture', 'name': 'Stale', 'revision': 1,
        'subject': 'Hello ${name}', 'body': '', 'variables': ['name']}, format='json').status_code == 409
    assert admin_client.delete(BASE + identifier + '/').status_code == 405


@pytest.mark.parametrize('extra', [ {'subject': 'Header\nInjected'}, {'variables': ['name', 'name']},
    {'subject': '${user.password}', 'variables': ['name']}, {'variables': ['unused']}, {'subject': '$broken{'},
    {'smtp_password': 'private'}, {'variables': ['Name']} ])
def test_invalid_template_rejected_without_version(admin_client, extra):
    assert template(admin_client, **extra).status_code == 400
    assert not MessageTemplate.objects.exists()


def test_dispatch_inapp_idempotency_payload_and_fixed_old_version(admin_client, member_user):
    identifier = template(admin_client).json()['data']['id']
    response = send(admin_client, identifier, member_user)
    assert response.status_code == 202
    assert send(admin_client, identifier, member_user).status_code == 202
    assert MessageDelivery.objects.count() == OutboxEvent.objects.filter(topic='notification.delivery').count() == 1
    event = OutboxEvent.objects.get(topic='notification.delivery')
    assert set(event.payload) == {'delivery_id'}
    admin_client.patch(BASE + identifier + '/', {'code': 'fixture', 'name': 'Changed', 'revision': 1,
        'enabled': True, 'subject': 'Changed ${name}', 'body': '', 'variables': ['name']}, format='json')
    assert dispatch_outbox()['processed'] == 1, list(OutboxEvent.objects.values('status', 'last_error'))
    row = MessageDelivery.objects.get()
    assert row.status == 'succeeded' and row.version.number == 1
    assert Notification.objects.get().title == 'Hello private fixture'
    assert dispatch_outbox()['processed'] == 0 and Notification.objects.count() == 1
    data = admin_client.get(DELIVERIES).json()['data']['items'][0]
    assert not {'subject', 'body', 'email_binding', 'actor_session_id'} & set(data)
    assert 'private fixture' not in str(list(OperationLog.objects.filter(resource='message_delivery').values()))


def test_disabled_email_rejects_entire_batch(admin_client, member_user):
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user, channels=['inapp', 'email']).status_code == 400
    assert not MessageDelivery.objects.exists() and not OutboxEvent.objects.filter(topic='notification.delivery').exists()


@override_settings(NOTIFICATION_EMAIL_ENABLED=True, EMAIL_HOST='smtp.fixture', DEFAULT_FROM_EMAIL='sender@example.test', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
def test_verified_email_required_and_delivery_no_raw_address(admin_client, member_user):
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user, channels=['email']).status_code == 400
    member_user.verified_email = member_user.email
    member_user.save(update_fields=['verified_email'])
    assert send(admin_client, identifier, member_user, channels=['email']).status_code == 202
    assert dispatch_outbox()['processed'] == 1
    assert len(mail.outbox) == 1 and mail.outbox[0].to == [member_user.email]
    row = MessageDelivery.objects.get()
    assert row.status == 'succeeded' and 'Message-ID' in mail.outbox[0].extra_headers
    assert member_user.email not in str(row.__dict__)


@override_settings(NOTIFICATION_EMAIL_ENABLED=True, EMAIL_HOST='smtp.fixture', DEFAULT_FROM_EMAIL='sender@example.test')
def test_failure_record_safe_five_attempt_limit_and_manual_retry(admin_client, member_user):
    identifier = template(admin_client).json()['data']['id']
    member_user.verified_email = member_user.email
    member_user.save(update_fields=['verified_email'])
    assert send(admin_client, identifier, member_user, channels=['email']).status_code == 202
    row = MessageDelivery.objects.get()
    with patch('apps.notifications.message_channels.EmailMessage.send', side_effect=RuntimeError('smtp password private')):
        for count in range(1, 6):
            OutboxEvent.objects.filter(topic='notification.delivery').update(available_at=timezone.now()-timedelta(seconds=1))
            assert dispatch_outbox()['failed'] == 1
            row.refresh_from_db()
            assert row.status == 'failed' and row.attempts == count and row.last_error == 'channel_delivery_failed'
            if count == 1:
                response = admin_client.post(DELIVERIES + str(row.pk) + '/retry/', {}, format='json')
                assert response.status_code == 200 and response.json()['data']['attempts'] == 1
        OutboxEvent.objects.filter(topic='notification.delivery').update(available_at=timezone.now()-timedelta(seconds=1))
        assert dispatch_outbox() == {'processed': 0, 'failed': 0}
    assert admin_client.post(DELIVERIES + str(row.pk) + '/retry/', {}, format='json').status_code == 400
    event = OutboxEvent.objects.get(topic='notification.delivery')
    assert 'private' not in event.last_error
    assert admin_client.post('/api/v1/reliability/events/' + str(event.pk) + '/retry/', {}, format='json').status_code == 409


@pytest.mark.parametrize('change', ['template', 'module', 'recipient', 'actor', 'session', 'expired'])
def test_revoked_or_disabled_pending_delivery_terminates_without_side_effect(admin_client, admin_user, member_user, change):
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user).status_code == 202
    row = MessageDelivery.objects.get()
    if change == 'template': MessageTemplate.objects.update(enabled=False)
    if change == 'recipient': member_user.is_active=False; member_user.save()
    if change == 'actor': admin_user.session_version += 1; admin_user.save()
    if change == 'session':
        from apps.auth_app.models import AuthSession
        AuthSession.objects.filter(pk=row.actor_session_id).update(revoked_at=timezone.now())
    if change == 'expired': MessageDelivery.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
    with override_settings(ADMINCORE_MODULES=() if change == 'module' else ['notifications']):
        assert dispatch_outbox()['processed'] == 1
    row.refresh_from_db()
    assert row.status == 'terminated' and row.attempts == 0 and row.last_error
    assert not Notification.objects.exists()


def test_variable_schema_duplicates_and_audit_failure_roll_back_batch(admin_client, member_user):
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user, values={'missing': 'value'}).status_code == 400
    assert send(admin_client, identifier, member_user, recipient_ids=[str(member_user.pk)] * 2).status_code == 400
    with patch('apps.notifications.message_services.write_audit', side_effect=RuntimeError('private fixture')):
        assert send(admin_client, identifier, member_user).status_code == 500
    assert not MessageDelivery.objects.exists() and not OutboxEvent.objects.filter(topic='notification.delivery').exists()


def test_anonymous_and_member_cannot_manage_templates_or_deliveries(member_client):
    assert member_client.get(BASE).status_code == 403
    assert member_client.get(DELIVERIES).status_code == 403


def test_revoked_sender_cannot_replay_successful_submission(admin_client, admin_user, member_user):
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user).status_code == 202
    type(admin_user).objects.filter(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
    assert send(admin_client, identifier, member_user).status_code == 403
    assert MessageDelivery.objects.count() == 1


def test_module_routes_closed_and_reenabled_history_preserved(admin_client):
    identifier = template(admin_client).json()['data']['id']
    with override_settings(ADMINCORE_MODULES=()):
        assert admin_client.get(BASE).status_code == 404
        assert admin_client.get(DELIVERIES).status_code == 404
    assert admin_client.get(BASE + identifier + '/').status_code == 200
    assert MessageTemplateVersion.objects.count() == 1


def test_history_response_paged_and_current_version_query_bounded(admin_client):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    identifier = template(admin_client).json()['data']['id']
    response = admin_client.get(BASE + identifier + '/versions/')
    assert response.status_code == 200 and response.json()['data']['pagination']['total'] == 1
    with CaptureQueriesContext(connection) as captured:
        response = admin_client.get(BASE)
    assert response.status_code == 200
    version_queries = [query['sql'] for query in captured if 'notifications_messagetemplateversion' in query['sql']]
    assert len(version_queries) == 1 and 'revision' in version_queries[0]
