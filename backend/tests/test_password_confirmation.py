"""单次密码确认的凭据、限流和保密边界。"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, Throttled, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.auth_app.models import AuthSession
from apps.auth_app.reauthentication import PasswordConfirmationUnavailable, require_recent_password
from apps.auth_app.sessions import issue_session
from apps.logs.models import OperationLog

PASSWORD = 'Member#12345'


@pytest.fixture
def confirmation_request(member_user):
    token = issue_session(member_user)

    def make(data=None, *, content_type='application/json'):
        factory = APIRequestFactory()
        if content_type == 'application/json':
            raw = factory.post('/', data if data is not None else {'current_password': PASSWORD}, format='json')
        else:
            raw = factory.post('/', data or {'current_password': PASSWORD})
        force_authenticate(raw, user=member_user, token=token.access_token)
        return Request(raw, parsers=[JSONParser()])
    return make


@pytest.mark.django_db
def test_correct_password_returns_only_current_session(confirmation_request, member_user):
    before = OperationLog.objects.count()
    with transaction.atomic():
        session = require_recent_password(confirmation_request(), member_user, 'session:revoke')
    assert isinstance(session, AuthSession)
    assert session.user_id == member_user.pk
    assert OperationLog.objects.count() == before
    assert cache.get('current_password') is None


@pytest.mark.django_db
@pytest.mark.parametrize('data', [{}, {'current_password': None}, {'current_password': 123},
                                 {'current_password': ''}, {'current_password': 'x' * 4097}, []])
def test_missing_or_malformed_password_is_400(data, confirmation_request, member_user):
    with transaction.atomic(), pytest.raises(ValidationError) as error:
        require_recent_password(confirmation_request(data), member_user, 'session:revoke')
    assert error.value.status_code == 400


@pytest.mark.django_db
def test_non_json_password_is_400(confirmation_request, member_user):
    with transaction.atomic(), pytest.raises(ValidationError):
        require_recent_password(confirmation_request(content_type='multipart/form-data'), member_user, 'session:revoke')


@pytest.mark.django_db
def test_wrong_password_never_appears_in_error_or_logs(confirmation_request, member_user):
    secret = 'wrong-private-value'
    with transaction.atomic(), pytest.raises(PermissionDenied) as error:
        require_recent_password(confirmation_request({'current_password': secret}), member_user, 'session:revoke')
    assert error.value.status_code == 403
    assert secret not in str(error.value.detail)
    assert not OperationLog.objects.exists()


@pytest.mark.django_db
@override_settings(AUTH_REAUTH_SCOPE_FAILURE_LIMIT=2, AUTH_REAUTH_USER_FAILURE_LIMIT=3)
def test_scope_and_global_user_limits(confirmation_request, member_user):
    with patch('apps.auth_app.reauthentication.time.time', return_value=600):
        for _ in range(2):
            with transaction.atomic(), pytest.raises(PermissionDenied):
                require_recent_password(confirmation_request({'current_password': 'wrong'}), member_user, 'session:revoke')
        with transaction.atomic(), pytest.raises(Throttled) as error:
            require_recent_password(confirmation_request(), member_user, 'session:revoke')
        assert error.value.wait == 60
        with transaction.atomic():
            require_recent_password(confirmation_request(), member_user, 'session:revoke-others')
        with transaction.atomic(), pytest.raises(PermissionDenied):
            require_recent_password(confirmation_request({'current_password': 'wrong'}), member_user, 'session:revoke-others')
        with transaction.atomic(), pytest.raises(Throttled):
            require_recent_password(confirmation_request(), member_user, 'session:admin-revoke-all')
    with patch('apps.auth_app.reauthentication.time.time', return_value=660), transaction.atomic():
        require_recent_password(confirmation_request(), member_user, 'session:revoke')


@pytest.mark.django_db
def test_success_does_not_reset_failures_or_reuse_confirmation(confirmation_request, member_user):
    with override_settings(AUTH_REAUTH_SCOPE_FAILURE_LIMIT=2), transaction.atomic():
        with pytest.raises(PermissionDenied):
            require_recent_password(confirmation_request({'current_password': 'wrong'}), member_user, 'session:revoke')
        require_recent_password(confirmation_request(), member_user, 'session:revoke')
        with pytest.raises(ValidationError):
            require_recent_password(confirmation_request({}), member_user, 'session:revoke')
        with pytest.raises(PermissionDenied):
            require_recent_password(confirmation_request({'current_password': 'wrong'}), member_user, 'session:revoke')
        with pytest.raises(Throttled):
            require_recent_password(confirmation_request(), member_user, 'session:revoke')


@pytest.mark.django_db
@pytest.mark.parametrize('change', ['revoked', 'expired', 'idle', 'inactive', 'password', 'version'])
def test_correct_password_cannot_bypass_invalid_session(change, confirmation_request, member_user):
    request = confirmation_request()
    session = AuthSession.objects.get(user=member_user)
    if change == 'revoked':
        session.revoked_at = timezone.now()
    elif change == 'expired':
        session.expires_at = timezone.now() - timedelta(seconds=1)
    elif change == 'idle':
        session.last_seen_at = timezone.now() - timedelta(days=2)
    elif change == 'inactive':
        type(member_user).objects.filter(pk=member_user.pk).update(is_active=False)
    elif change == 'password':
        fresh = type(member_user).objects.get(pk=member_user.pk)
        fresh.set_password('New#LongPassword123')
        fresh.save(update_fields=['password'])
    else:
        type(member_user).objects.filter(pk=member_user.pk).update(session_version=1)
    session.save()
    with transaction.atomic(), pytest.raises(AuthenticationFailed):
        require_recent_password(request, member_user, 'session:revoke')


@pytest.mark.django_db
def test_other_actor_cannot_confirm_request(confirmation_request, member_user, admin_user):
    with transaction.atomic(), pytest.raises(AuthenticationFailed):
        require_recent_password(confirmation_request(), admin_user, 'session:revoke')


@pytest.mark.django_db
def test_cache_failure_is_closed_and_does_not_expose_exception(confirmation_request, member_user):
    with patch('apps.auth_app.reauthentication.cache.get', side_effect=RuntimeError('private-cache-url')):
        with transaction.atomic(), pytest.raises(PasswordConfirmationUnavailable) as error:
            require_recent_password(confirmation_request(), member_user, 'session:revoke')
    assert error.value.status_code == 503
    assert 'private-cache-url' not in str(error.value.detail)


@pytest.mark.django_db
def test_failure_counter_write_error_also_fails_closed(confirmation_request, member_user):
    with patch('apps.auth_app.reauthentication.cache.add', side_effect=RuntimeError('private-cache-url')):
        with transaction.atomic(), pytest.raises(PasswordConfirmationUnavailable) as error:
            require_recent_password(confirmation_request({'current_password': 'wrong'}), member_user, 'session:revoke')
    assert 'private-cache-url' not in str(error.value.detail)


@pytest.mark.django_db
def test_deleted_actor_cannot_use_stale_object(confirmation_request, member_user):
    request = confirmation_request()
    type(member_user).objects.filter(pk=member_user.pk).delete()
    with transaction.atomic(), pytest.raises(AuthenticationFailed):
        require_recent_password(request, member_user, 'session:revoke')


@pytest.mark.django_db
def test_scope_cannot_be_supplied_by_client(confirmation_request, member_user):
    with transaction.atomic(), pytest.raises(ValueError):
        require_recent_password(confirmation_request(), member_user, 'client-picked-scope')


@pytest.mark.django_db(transaction=True)
def test_caller_must_keep_sensitive_action_in_transaction(confirmation_request, member_user):
    with pytest.raises(RuntimeError):
        require_recent_password(confirmation_request(), member_user, 'session:revoke')
