"""模板真实投递须复用企业会话边界，同时保留正常本地队列。"""
from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from apps.auth_app.models import AuthSession
from apps.notifications.message_services import deliver
from apps.notifications.models import MessageDelivery, MessageTemplate, MessageTemplateVersion, Notification
from tests.test_sso_session_boundary import bound, invalidate, CHANGES  # noqa: F401

pytestmark = pytest.mark.django_db


def queued(user, token, version):
    return MessageDelivery.objects.create(version=version, recipient=user, creator=user,
        channel='inapp', subject='Session boundary', body='Isolated queue fixture',
        actor_session_version=user.session_version, actor_session_id=token['sid'],
        expires_at=timezone.now() + timedelta(hours=1))


def version_for(user):
    row = MessageTemplate.objects.create(code='sso-boundary', name='Session boundary')
    return MessageTemplateVersion.objects.create(template=row, number=1, creator=user,
        subject='Session boundary', body='Isolated queue fixture', variables=[])


@pytest.mark.parametrize('change', CHANGES)
def test_real_delivery_terminates_invalid_enterprise_but_keeps_local(bound, settings, change):
    user, local, enterprise, link = bound
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'notifications')
    version = version_for(user)
    corporate, ordinary = queued(user, enterprise, version), queued(user, local, version)
    invalidate(settings, change, link)
    # module mutation from shared fixture removes SSO; notifications itself stays available.
    settings.ADMINCORE_MODULES = tuple(dict.fromkeys((*settings.ADMINCORE_MODULES, 'notifications')))
    with transaction.atomic():
        deliver({'delivery_id': str(corporate.pk)})
    corporate.refresh_from_db()
    assert (corporate.status, corporate.last_error, corporate.attempts, corporate.sent_at) == (
        'terminated', 'sender_session_revoked', 0, None)
    assert not Notification.objects.exists()
    with transaction.atomic():
        deliver({'delivery_id': str(ordinary.pk)})
    ordinary.refresh_from_db()
    assert ordinary.status == 'succeeded' and ordinary.attempts == 1 and ordinary.sent_at
    assert Notification.objects.count() == 1
    assert Notification.objects.get().recipient_id == user.pk
    # A terminal corporate delivery cannot revive or produce a duplicate later.
    with transaction.atomic():
        deliver({'delivery_id': str(corporate.pk)})
    assert Notification.objects.count() == 1


def test_valid_enterprise_delivery_still_succeeds(bound, settings):
    user, _, enterprise, _ = bound
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'notifications')
    row = queued(user, enterprise, version_for(user))
    with transaction.atomic():
        deliver({'delivery_id': str(row.pk)})
    row.refresh_from_db()
    assert row.status == 'succeeded' and row.attempts == 1 and Notification.objects.count() == 1


@pytest.mark.parametrize('field,value', [('session_version', 999), ('password_hash', 'invalid-hash')])
def test_sender_session_credential_snapshot_remains_enforced(bound, settings, field, value):
    user, local, _, _ = bound
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'notifications')
    row = queued(user, local, version_for(user))
    AuthSession.objects.filter(pk=local['sid']).update(**{field: value})
    with transaction.atomic():
        deliver({'delivery_id': str(row.pk)})
    row.refresh_from_db()
    assert row.status == 'terminated' and row.last_error == 'sender_session_revoked' and row.attempts == 0
    assert not Notification.objects.exists()
