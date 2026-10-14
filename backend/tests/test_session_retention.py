"""失效设备清理只回收超过保留期的记录，分批限制单次工作量。"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session
from apps.core.tasks import cleanup_expired_sessions


@pytest.mark.django_db
def test_retention_keeps_active_recent_and_batches_expired(member_user):
    tokens = [issue_session(member_user) for _ in range(5)]
    now = timezone.now()
    AuthSession.objects.filter(pk=tokens[0]['sid']).update(expires_at=now - timedelta(days=31))
    AuthSession.objects.filter(pk=tokens[1]['sid']).update(revoked_at=now - timedelta(days=31))
    AuthSession.objects.filter(pk=tokens[2]['sid']).update(expires_at=now - timedelta(days=29))
    AuthSession.objects.filter(pk=tokens[3]['sid']).update(revoked_at=now)
    OutstandingToken.objects.filter(jti__in=[tokens[0]['jti'], tokens[1]['jti']]).update(
        expires_at=now - timedelta(days=31))
    result = cleanup_expired_sessions(batch_size=1)
    assert result == {'deleted_sessions': 1, 'deleted_refresh_records': 1}
    assert cleanup_expired_sessions()['deleted_sessions'] == 1
    assert set(str(pk) for pk in AuthSession.objects.values_list('pk', flat=True)) == {
        tokens[index]['sid'] for index in [2, 3, 4]}
    assert OutstandingToken.objects.count() == 3
    assert cleanup_expired_sessions() == {'deleted_sessions': 0, 'deleted_refresh_records': 0}


@pytest.mark.parametrize('batch', [0, 1001, True, '100', None])
def test_retention_rejects_unbounded_batches(batch):
    with pytest.raises(ValueError):
        cleanup_expired_sessions(batch_size=batch)
