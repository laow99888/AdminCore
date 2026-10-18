from datetime import datetime, time, timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import OutboxEvent, Tenant, TenantMembership
from apps.core.tasks import dispatch_outbox
from apps.core.tenancy import tenant_context
from apps.logs.models import OperationLog
from apps.notifications.models import Notification, NotificationPreference, MessageDelivery
from apps.notifications.preferences import DeliveryDeferred, OPTIONAL_EVENTS, preference_for, quiet_until
from apps.notifications.message_services import prepare_delivery
from tests.test_message_templates import send, template

pytestmark = pytest.mark.django_db
URL = '/api/v1/notifications/preferences/'


def body(**extra):
    return {'revision': 0, 'subscriptions': list(OPTIONAL_EVENTS), 'channels': ['inapp', 'email', 'webhook', 'sms'],
            'quiet_enabled': False, 'quiet_start': '22:00', 'quiet_end': '08:00', 'timezone': 'Asia/Shanghai', **extra}


def test_read_defaults_does_not_create_and_self_only(member_client, admin_client):
    response = member_client.get(URL)
    assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
    data = response.json()['data']
    assert data['revision'] == 0 and data['available_channels'] == ['inapp']
    assert [event['code'] for event in data['events'] if event['required']] == ['system.notice', 'approval.action', 'task.result']
    assert not NotificationPreference.objects.exists()
    assert member_client.put(URL, body(channels=[]), format='json').status_code == 200
    assert admin_client.get(URL).json()['data']['channels'] == ['inapp', 'email', 'webhook', 'sms']
    assert APIClient().get(URL).status_code == 401


def test_update_revision_and_audit_failure_rolls_back(member_client, member_user):
    response = member_client.put(URL, body(channels=['inapp']), format='json')
    assert response.status_code == 200 and response.json()['data']['revision'] == 1
    assert OperationLog.objects.filter(resource='notification_preference', user=member_user).exists()
    assert member_client.put(URL, body(), format='json').status_code == 409
    with patch('apps.notifications.preference_views.write_audit', side_effect=RuntimeError('fixture')):
        assert member_client.put(URL, body(revision=1, channels=[]), format='json').status_code == 500
    row = NotificationPreference.objects.get(user=member_user)
    assert row.revision == 1 and row.channels == ['inapp']
    assert member_client.put(URL, body(revision=1, channels=['email']), format='json').json()['data']['revision'] == 2
    assert NotificationPreference.objects.count() == 1


@pytest.mark.parametrize('extra', [
    {'user': 'other'}, {'tenant': 'other'}, {'subscriptions': ['system.notice']},
    {'subscriptions': ['unregistered']}, {'channels': ['fax']}, {'channels': ['email', 'email']},
    {'subscriptions': ['template.message', 'template.message']}, {'timezone': 'Invalid/Fixture'},
    {'timezone': '/etc/passwd'}, {'quiet_start': '22:00:01'}, {'quiet_start': '08:00'}, {'revision': -1},
])
def test_rejects_unregistered_and_invalid_settings(member_client, extra):
    assert member_client.put(URL, body(**extra), format='json').status_code == 400
    assert not NotificationPreference.objects.exists()


def test_current_device_reauthorization_precedes_write(member_client, member_user):
    type(member_user).objects.filter(pk=member_user.pk).update(must_change_password=True)
    assert member_client.put(URL, body(), format='json').status_code == 403
    assert not NotificationPreference.objects.exists()


def test_disabled_module_closes_preferences(member_client):
    with override_settings(ADMINCORE_MODULES=()):
        assert member_client.get(URL).status_code == 404
        assert member_client.put(URL, body(), format='json').status_code == 404


def test_required_inbox_notifications_bypass_all_opt_out(member_user):
    NotificationPreference.objects.create(user=member_user, subscriptions=[], channels=[], quiet_enabled=True)
    for kind in ['system', 'approval', 'task']:
        assert Notification.push([member_user.pk], kind, notification_type=kind) == 1
    assert Notification.push([member_user.pk], 'optional', notification_type='announcement') == 0
    assert Notification.push([member_user.pk], 'optional', event_code='business.update') == 0
    with pytest.raises(ValueError, match='unregistered_notification_event'):
        Notification.push([member_user.pk], 'unknown', event_code='typo')
    assert Notification.objects.count() == 3


def test_optional_inbox_subscriptions_channels_dedupe_and_no_quiet_delay(member_user):
    row = NotificationPreference.objects.create(user=member_user, channels=['inapp'], subscriptions=['business.update'], quiet_enabled=True)
    assert Notification.push([member_user.pk], 'update', event_code='business.update', dedupe_key='fixture') == 1
    assert Notification.push([member_user.pk], 'update', event_code='business.update', dedupe_key='fixture') == 0
    assert Notification.push([member_user.pk], 'announcement', notification_type='announcement') == 0
    row.channels = []; row.save()
    assert Notification.push([member_user.pk], 'update', event_code='business.update') == 0


@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_preferences_isolated_by_tenant_and_null_scope(member_user):
    first = Tenant.objects.create(slug='first', name='First')
    second = Tenant.objects.create(slug='second', name='Second')
    TenantMembership.objects.create(tenant=first, user=member_user)
    TenantMembership.objects.create(tenant=second, user=member_user)
    with tenant_context(first.pk):
        row = NotificationPreference.objects.create(user=member_user, channels=[])
        assert preference_for(member_user.pk).pk == row.pk
    with tenant_context(second.pk):
        assert preference_for(member_user.pk) is None
        assert Notification.push([member_user.pk], 'optional', event_code='business.update') == 1
        assert Notification.objects.get().tenant_id == second.pk
        second_row = NotificationPreference.objects.create(user=member_user)
        assert preference_for(member_user.pk).pk == second_row.pk
    assert preference_for(member_user.pk) is None
    NotificationPreference.objects.create(user=member_user)
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationPreference.objects.create(user=member_user)
    with tenant_context(first.pk):
        with pytest.raises(IntegrityError), transaction.atomic():
            NotificationPreference.objects.create(user=member_user)


@pytest.mark.parametrize('start,end,instant,expected', [
    ('22:00', '08:00', '2026-10-18T13:59:00+00:00', None),
    ('22:00', '08:00', '2026-10-18T14:00:01+00:00', '2026-10-19T00:00:00+00:00'),
    ('22:00', '08:00', '2026-10-18T23:59:59+00:00', '2026-10-19T00:00:00+00:00'),
    ('22:00', '08:00', '2026-10-19T00:00:00+00:00', None),
    ('09:00', '12:00', '2026-10-18T02:00:00+00:00', '2026-10-18T04:00:00+00:00'),
])
def test_quiet_hours_boundaries_and_cross_midnight(member_user, start, end, instant, expected):
    row = NotificationPreference(user=member_user, quiet_enabled=True, quiet_start=time.fromisoformat(start), quiet_end=time.fromisoformat(end))
    result = quiet_until(row, datetime.fromisoformat(instant))
    assert result == (datetime.fromisoformat(expected) if expected else None)
    row.quiet_enabled = False
    assert quiet_until(row, datetime.fromisoformat(instant)) is None
    assert quiet_until(None) is None


@pytest.mark.parametrize('instant,expected', [
    ('2026-03-08T06:30:00+00:00', '2026-03-08T12:00:00+00:00'),
    ('2026-11-01T05:30:00+00:00', '2026-11-01T13:00:00+00:00'),
    ('2026-11-01T06:30:00+00:00', '2026-11-01T13:00:00+00:00'),
])
def test_quiet_hours_daylight_saving_transition(member_user, instant, expected):
    row = NotificationPreference(user=member_user, quiet_enabled=True, timezone='America/New_York')
    assert quiet_until(row, datetime.fromisoformat(instant)) == datetime.fromisoformat(expected)


@pytest.mark.parametrize('channels,subscriptions', [([], list(OPTIONAL_EVENTS)), (['inapp'], [])])
def test_template_preference_revoked_after_submission_no_delivery_attempt(admin_client, member_user, channels, subscriptions):
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user).status_code == 202
    NotificationPreference.objects.create(user=member_user, channels=channels, subscriptions=subscriptions)
    assert dispatch_outbox()['processed'] == 1
    row = MessageDelivery.objects.get()
    assert row.status == 'terminated' and row.last_error == 'recipient_preference_disabled' and row.attempts == 0
    assert not Notification.objects.exists()


EMAIL_SETTINGS = {'NOTIFICATION_EMAIL_ENABLED': True, 'EMAIL_HOST': 'smtp.fixture', 'DEFAULT_FROM_EMAIL': 'sender@example.test',
                  'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}


@override_settings(**EMAIL_SETTINGS)
def test_defer_external_delivery_does_not_spend_attempts_and_revocation_wins(admin_client, admin_user, member_user):
    member_user.verified_email = member_user.email; member_user.save(update_fields=['verified_email'])
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user, channels=['email']).status_code == 202
    NotificationPreference.objects.create(user=member_user, quiet_enabled=True)
    row = MessageDelivery.objects.get()
    now = timezone.now()
    until = now + timedelta(minutes=10)
    with patch('apps.notifications.preferences.quiet_until', return_value=until):
        with pytest.raises(DeliveryDeferred) as error:
            prepare_delivery({'delivery_id': str(row.pk)})
        assert error.value.until == until
        row.refresh_from_db(); assert row.status == 'pending' and row.attempts == 0
        type(admin_user).objects.filter(pk=admin_user.pk).update(session_version=admin_user.session_version + 1)
        assert prepare_delivery({'delivery_id': str(row.pk)}) is None
    row.refresh_from_db()
    assert row.status == 'terminated' and row.last_error == 'sender_revoked' and row.attempts == 0


@override_settings(**EMAIL_SETTINGS)
def test_dispatcher_quiet_deferral_and_resume_without_attempt_penalty(admin_client, member_user):
    from django.core import mail
    member_user.verified_email = member_user.email; member_user.save(update_fields=['verified_email'])
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user, channels=['email']).status_code == 202
    NotificationPreference.objects.create(user=member_user, quiet_enabled=True)
    until = timezone.now() + timedelta(minutes=10)
    with patch('apps.notifications.preferences.quiet_until', return_value=until):
        assert dispatch_outbox() == {'processed': 0, 'failed': 0}
    row = MessageDelivery.objects.get(); event = OutboxEvent.objects.get(topic='notification.delivery')
    assert row.status == 'pending' and row.attempts == event.attempts == 0
    assert event.status == 'pending' and event.available_at == until and not event.last_error
    OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now() - timedelta(seconds=1))
    with patch('apps.notifications.preferences.quiet_until', return_value=None):
        assert dispatch_outbox()['processed'] == 1
    row.refresh_from_db(); event.refresh_from_db()
    assert row.status == 'succeeded' and row.attempts == event.attempts == 1 and len(mail.outbox) == 1


@override_settings(**EMAIL_SETTINGS)
def test_quiet_deferral_capped_at_original_expiry(admin_client, member_user):
    member_user.verified_email = member_user.email; member_user.save(update_fields=['verified_email'])
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user, channels=['email']).status_code == 202
    NotificationPreference.objects.create(user=member_user, quiet_enabled=True)
    row = MessageDelivery.objects.get()
    with patch('apps.notifications.preferences.quiet_until', return_value=row.expires_at + timedelta(hours=2)):
        with pytest.raises(DeliveryDeferred) as error:
            prepare_delivery({'delivery_id': str(row.pk)})
        assert error.value.until == row.expires_at
    MessageDelivery.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    with patch('apps.notifications.preferences.quiet_until', return_value=timezone.now() + timedelta(hours=3)):
        assert prepare_delivery({'delivery_id': str(row.pk)}) is None
    row.refresh_from_db(); assert row.last_error == 'delivery_expired' and row.attempts == 0


@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
@pytest.mark.parametrize('revoked', ['membership', 'closed', 'suspended'])
def test_tenant_background_delivery_checks_membership_and_status_before_preferences(admin_client, member_user, revoked):
    tenant = Tenant.objects.create(slug='delivery', name='Delivery')
    membership = TenantMembership.objects.create(tenant=tenant, user=member_user)
    admin_client.defaults['HTTP_X_ADMINCORE_TENANT'] = str(tenant.pk)
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user).status_code == 202
    with tenant_context(tenant.pk):
        NotificationPreference.objects.create(user=member_user, channels=[])
    if revoked == 'membership':
        membership.is_active = False; membership.save(update_fields=['is_active'])
    else:
        tenant.status = revoked; tenant.save(update_fields=['status'])
    assert dispatch_outbox()['processed'] == 1
    row = MessageDelivery.all_objects.get()
    assert row.status == 'terminated' and row.last_error == 'delivery_tenant_unavailable' and row.attempts == 0
    assert not Notification.all_objects.exists()


@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_background_delivery_uses_record_tenant_preference_not_other_tenant(admin_client, member_user):
    first = Tenant.objects.create(slug='firstdelivery', name='First')
    second = Tenant.objects.create(slug='seconddelivery', name='Second')
    TenantMembership.objects.create(tenant=first, user=member_user)
    TenantMembership.objects.create(tenant=second, user=member_user)
    admin_client.defaults['HTTP_X_ADMINCORE_TENANT'] = str(first.pk)
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user).status_code == 202
    with tenant_context(second.pk):
        NotificationPreference.objects.create(user=member_user, channels=[])
    assert dispatch_outbox()['processed'] == 1
    row = MessageDelivery.all_objects.get(); notification = Notification.all_objects.get()
    assert row.status == 'succeeded' and row.tenant_id == notification.tenant_id == first.pk


@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_push_rechecks_tenant_active_members_even_for_required_notifications(member_user, admin_user):
    tenant = Tenant.objects.create(slug='pushmembership', name='Push')
    membership = TenantMembership.objects.create(tenant=tenant, user=member_user)
    with tenant_context(tenant.pk):
        assert Notification.push([member_user.pk, admin_user.pk], 'required') == 1
        membership.is_active = False; membership.save(update_fields=['is_active'])
        assert Notification.push([member_user.pk], 'required') == 0
        membership.is_active = True; membership.save(update_fields=['is_active'])
        tenant.status = Tenant.STATUS_SUSPENDED; tenant.save(update_fields=['status'])
        assert Notification.push([member_user.pk], 'required') == 0
    assert Notification.all_objects.count() == 1


@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True, **EMAIL_SETTINGS)
@pytest.mark.parametrize('revoked', ['membership', 'closed', 'suspended'])
def test_deferred_tenant_delivery_rechecks_authorization_before_resume(admin_client, member_user, revoked):
    from django.core import mail
    tenant = Tenant.objects.create(slug='deferredmembership', name='Deferred')
    membership = TenantMembership.objects.create(tenant=tenant, user=member_user)
    member_user.verified_email = member_user.email; member_user.save(update_fields=['verified_email'])
    admin_client.defaults['HTTP_X_ADMINCORE_TENANT'] = str(tenant.pk)
    identifier = template(admin_client).json()['data']['id']
    assert send(admin_client, identifier, member_user, channels=['email']).status_code == 202
    with tenant_context(tenant.pk):
        NotificationPreference.objects.create(user=member_user, quiet_enabled=True)
    until = timezone.now() + timedelta(minutes=10)
    with patch('apps.notifications.preferences.quiet_until', return_value=until):
        assert dispatch_outbox() == {'processed': 0, 'failed': 0}
    row = MessageDelivery.all_objects.get(); event = OutboxEvent.all_objects.get(topic='notification.delivery')
    assert row.attempts == event.attempts == 0
    if revoked == 'membership':
        membership.is_active = False; membership.save(update_fields=['is_active'])
    else:
        tenant.status = revoked; tenant.save(update_fields=['status'])
    OutboxEvent.all_objects.filter(pk=event.pk).update(available_at=timezone.now() - timedelta(seconds=1))
    with patch('apps.notifications.preferences.quiet_until', return_value=None):
        assert dispatch_outbox()['processed'] == 1
    row.refresh_from_db(); event.refresh_from_db()
    assert row.status == 'terminated' and row.last_error == 'delivery_tenant_unavailable' and row.attempts == 0
    assert event.status == 'succeeded' and len(mail.outbox) == 0
