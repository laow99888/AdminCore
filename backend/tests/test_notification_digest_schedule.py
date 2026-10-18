"""摘要定时调度必须可裁剪、幂等录入并真实刷新已到期记录。"""
from datetime import timedelta
from io import StringIO

import pytest
from celery.exceptions import Ignore
from django.core.management import call_command
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from apps.notifications import digests
from apps.notifications.models import BusinessNotice, NotificationPreference
from apps.notifications.tasks import refresh_digests
from tests.test_notification_digests import business  # noqa: F401

pytestmark = pytest.mark.django_db


def test_schedule_is_enabled_idempotent_and_preserves_operator_settings(settings):
    call_command('configure_maintenance', stdout=StringIO())
    entry = PeriodicTask.objects.get(task='notifications.refresh_digests')
    assert entry.enabled and entry.crontab.minute == '*' and entry.crontab.hour == '*'
    entry.enabled = False
    entry.kwargs = '{"limit": 25}'
    entry.save()
    call_command('configure_maintenance', stdout=StringIO())
    entry.refresh_from_db()
    assert not entry.enabled and entry.kwargs == '{"limit": 25}'
    assert PeriodicTask.objects.filter(task='notifications.refresh_digests').count() == 1
    PeriodicTask.objects.filter(pk=entry.pk).delete()
    settings.ADMINCORE_MODULES = ()
    call_command('configure_maintenance', stdout=StringIO())
    assert not PeriodicTask.objects.filter(task='notifications.refresh_digests').exists()
    with pytest.raises(Ignore):
        refresh_digests()


def test_celery_entry_only_flushes_due_and_repeated_runs_do_not_duplicate(business, member_user):
    source, _ = business
    now = timezone.now()
    NotificationPreference.objects.create(user=member_user, business_delivery_mode='digest')
    due, _ = digests.enqueue_business_notice(member_user, 'example', source.pk, 'due', now=now - timedelta(hours=2))
    waiting, _ = digests.enqueue_business_notice(member_user, 'example', source.pk, 'waiting', now=now)
    first = refresh_digests(limit=1)
    assert first == {'processed': 1, 'published': 1, 'suppressed': 0, 'summaries': 1}
    assert refresh_digests(limit=1)['processed'] == 0
    due.refresh_from_db(); waiting.refresh_from_db()
    assert due.state == 'published' and waiting.state == 'pending'
    assert BusinessNotice.all_objects.filter(notification_id=due.notification_id).count() == 1


@pytest.mark.parametrize('limit', [True, 0, 501, '1', None])
def test_task_rejects_unbounded_or_non_integer_batches(limit):
    with pytest.raises(ValueError, match='1_to_500'):
        refresh_digests(limit=limit)
