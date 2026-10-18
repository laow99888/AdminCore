"""摘要接缝使用明确登记的测试适配器；鉴权、事务、租户和入箱使用真实模型。"""
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

import pytest
from django.core.management import call_command, CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.core.models import OutboxEvent, Tenant, TenantMembership
from apps.core.tenancy import tenant_context
from apps.notifications import digests
from apps.notifications.models import BusinessNotice, Notification, NotificationPreference
from tests.test_notification_preferences import body

pytestmark = pytest.mark.django_db
ROOT = '/api/v1/notifications/'


@pytest.fixture
def business(monkeypatch, admin_user):
    row = Notification.all_objects.create(recipient=admin_user, title='SECRET business data')
    access = {'allowed': True}
    service = SimpleNamespace(visible=lambda actor: Notification.all_objects.all() if access['allowed'] else Notification.all_objects.none())
    monkeypatch.setattr(digests, 'registered_module', lambda key: ({'title': '测试业务'}, Notification, service))
    monkeypatch.setattr(digests, 'module_enabled', lambda key: True)
    monkeypatch.setattr(digests, 'has_permission_code', lambda actor, code: access['allowed'])
    return row, access


def test_legacy_preference_write_preserves_new_fields(member_client, member_user):
    assert member_client.put(ROOT + 'preferences/', body(business_delivery_mode='digest', digest_minutes=1440), format='json').status_code == 200
    response = member_client.put(ROOT + 'preferences/', body(revision=1, channels=['inapp']), format='json')
    assert response.status_code == 200
    assert response.json()['data']['business_delivery_mode'] == 'digest'
    assert response.json()['data']['digest_minutes'] == 1440
    assert member_client.put(ROOT + 'preferences/', body(revision=2, digest_minutes=30), format='json').status_code == 400
    assert NotificationPreference.objects.get(user=member_user).revision == 2


def test_immediate_dedupe_references_and_conflicting_key(business, member_user):
    source, access = business
    row, created = digests.enqueue_business_notice(member_user, 'example', source.pk, 'stable-event')
    assert created and row.state == 'published' and row.notification_id
    assert 'SECRET' not in row.notification.content + row.notification.title
    replay, created = digests.enqueue_business_notice(member_user, 'example', source.pk, 'stable-event')
    assert not created and replay.pk == row.pk
    assert Notification.all_objects.filter(recipient=member_user).count() == 1
    other = Notification.all_objects.create(recipient=member_user, title='Other')
    from apps.core.system_views import VersionConflict
    with pytest.raises(VersionConflict):
        digests.enqueue_business_notice(member_user, 'example', other.pk, 'stable-event')
    assert digests.digest_references(member_user, row.notification_id)['items'][0]['object_id'] == str(source.pk)
    access['allowed'] = False
    assert digests.digest_references(member_user, row.notification_id)['items'] == []
    with pytest.raises(NotFound):
        digests.enqueue_business_notice(member_user, 'example', source.pk, 'new-event')


def test_digest_waits_merges_and_repeat_refresh_is_noop(business, member_user):
    source, _ = business
    now = timezone.now()
    preference = NotificationPreference.objects.create(user=member_user, business_delivery_mode='digest')
    first, _ = digests.enqueue_business_notice(member_user, 'example', source.pk, 'one', now=now)
    second, _ = digests.enqueue_business_notice(member_user, 'example', source.pk, 'two', now=now)
    preference.digest_minutes = 1440; preference.save()
    assert first.due_at == now + timedelta(hours=1)
    assert digests.refresh_due(now=now)['processed'] == 0
    result = digests.refresh_due(now=now + timedelta(hours=1))
    assert result == {'processed': 2, 'published': 2, 'suppressed': 0, 'summaries': 1}
    first.refresh_from_db(); second.refresh_from_db()
    assert first.notification_id == second.notification_id
    assert len(digests.digest_references(member_user, first.notification_id)['items']) == 1
    assert digests.refresh_due(now=now + timedelta(days=1))['processed'] == 0


def test_bounded_refresh_and_publish_failure_are_transactional(business, member_user):
    source, _ = business
    now = timezone.now()
    NotificationPreference.objects.create(user=member_user, business_delivery_mode='digest')
    for number in range(3):
        digests.enqueue_business_notice(member_user, 'example', source.pk, str(number), now=now)
    due = now + timedelta(hours=1)
    with patch('apps.notifications.digests.Notification.all_objects.create', side_effect=RuntimeError('fixture')):
        with pytest.raises(RuntimeError):
            digests.refresh_due(limit=1, now=due)
    assert BusinessNotice.all_objects.filter(state='pending').count() == 3
    assert not Notification.all_objects.filter(recipient=member_user).exists()
    assert digests.refresh_due(limit=2, now=due) == {'processed': 2, 'published': 2, 'suppressed': 0, 'summaries': 1}
    assert BusinessNotice.all_objects.filter(state='pending').count() == 1
    assert digests.refresh_due(limit=2, now=due)['published'] == 1


@pytest.mark.parametrize('reason', ['unsubscribe', 'permission', 'expired', 'inactive', 'password'])
def test_due_refresh_suppresses_revoked_or_expired(business, member_user, reason):
    source, access = business
    now = timezone.now()
    preference = NotificationPreference.objects.create(user=member_user, business_delivery_mode='digest')
    row, _ = digests.enqueue_business_notice(member_user, 'example', source.pk, 'one', now=now)
    if reason == 'unsubscribe': preference.channels = []; preference.save()
    if reason == 'permission': access['allowed'] = False
    if reason == 'expired': BusinessNotice.all_objects.filter(pk=row.pk).update(expires_at=now)
    if reason in {'inactive', 'password'}:
        type(member_user).objects.filter(pk=member_user.pk).update(**({'is_active': False} if reason == 'inactive' else {'must_change_password': True}))
    assert digests.refresh_due(now=now + timedelta(hours=2)) == {'processed': 1, 'published': 0, 'suppressed': 1, 'summaries': 0}
    assert not Notification.all_objects.filter(recipient=member_user).exists()


@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
@pytest.mark.parametrize('reason', ['membership', 'tenant'])
def test_tenant_exit_and_pause_block_delivery_and_detail(business, member_user, reason):
    source, _ = business
    tenant = Tenant.objects.create(slug='digest', name='Digest')
    membership = TenantMembership.objects.create(tenant=tenant, user=member_user)
    Notification.all_objects.filter(pk=source.pk).update(tenant=tenant)
    with tenant_context(tenant.pk):
        NotificationPreference.all_objects.create(tenant=tenant, user=member_user, business_delivery_mode='digest')
        row, _ = digests.enqueue_business_notice(member_user, 'example', source.pk, 'one')
    if reason == 'membership': membership.is_active = False; membership.save()
    else: tenant.status = 'suspended'; tenant.save()
    counts = digests.refresh_due(all_tenants=True, now=timezone.now() + timedelta(hours=2))
    assert counts['suppressed'] == 1 and counts['published'] == 0
    row.refresh_from_db(); assert row.state == 'suppressed'


def test_http_permissions_self_refresh_and_atomic_submit(business, admin_client, member_client, member_user):
    source, _ = business
    payload = {'resource': 'example', 'object_id': str(source.pk), 'event_id': str(uuid4()), 'recipient_ids': [str(member_user.pk)]}
    assert member_client.post(ROOT + 'business-notices/', payload, format='json').status_code == 403
    response = admin_client.post(ROOT + 'business-notices/', payload, format='json')
    assert response.status_code == 200 and response.json()['data']['published'] == 1
    response = admin_client.post(ROOT + 'business-notices/', payload, format='json')
    assert response.json()['data']['replayed'] == 1
    row = BusinessNotice.all_objects.get()
    assert admin_client.get(ROOT + f'digests/{row.notification_id}/').status_code == 404
    assert member_client.get(ROOT + f'digests/{row.notification_id}/').status_code == 200
    assert member_client.post(ROOT + 'digests/refresh/', {'force': True}, format='json').status_code == 400
    assert member_client.get(ROOT + 'digests/status/').json()['data']['pending'] == 0
    payload['event_id'] = str(uuid4())
    with patch('apps.notifications.digest_views.write_audit', side_effect=RuntimeError('fixture')):
        assert admin_client.post(ROOT + 'business-notices/', payload, format='json').status_code == 500
    assert BusinessNotice.all_objects.count() == 1


def test_refresh_command_safe_bounds_and_no_future_send(business, member_user):
    source, _ = business
    NotificationPreference.objects.create(user=member_user, business_delivery_mode='digest')
    digests.enqueue_business_notice(member_user, 'example', source.pk, 'one')
    output = StringIO(); call_command('refresh_notification_digests', limit=1, stdout=output)
    assert '"processed": 0' in output.getvalue()
    with pytest.raises(CommandError): call_command('refresh_notification_digests', limit=501)
    with pytest.raises(CommandError): call_command('refresh_notification_digests', '--force')


@override_settings(ADMINCORE_MULTI_TENANT_ENABLED=True)
def test_operations_window_tenant_scope_and_no_delivery_claim(admin_client, member_client, admin_user, member_user):
    first = Tenant.objects.create(slug='stats-one', name='One')
    second = Tenant.objects.create(slug='stats-two', name='Two')
    TenantMembership.objects.create(tenant=first, user=member_user)
    for scope in [None, first.pk, second.pk]:
        Notification.all_objects.create(tenant_id=scope, recipient=admin_user, title='PRIVATE', is_read=scope == first.pk)
        OutboxEvent.all_objects.create(tenant_id=scope, topic='notification.created', event_key=str(uuid4()), payload={}, status='succeeded', available_at=timezone.now())
    old = Notification.all_objects.create(tenant=first, recipient=admin_user, title='OLD')
    Notification.all_objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))
    assert member_client.get(ROOT + 'operations/').status_code == 403
    data = admin_client.get(ROOT + 'operations/', HTTP_X_ADMINCORE_TENANT=str(first.pk)).json()['data']
    assert data['window_days'] == 7 and data['inbox_created'] == data['inbox_read'] == 1
    assert data['outbox'] == [{'status': 'succeeded', 'count': 1}]
    assert data['final_delivery_receipts_supported'] is False and 'PRIVATE' not in str(data)
    assert admin_client.get(ROOT + 'operations/').json()['data']['inbox_created'] == 1
    assert admin_client.get(ROOT + 'operations/?days=90', HTTP_X_ADMINCORE_TENANT=str(first.pk)).json()['data']['inbox_created'] == 2
    for query in ['days=91', 'days=0', 'days=7&days=1', 'days=7&tenant=other', 'days=' + '9' * 5000]:
        assert admin_client.get(ROOT + 'operations/?' + query).status_code == 400
