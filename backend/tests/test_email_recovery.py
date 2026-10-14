"""认证邮件的反枚举、归属、一次消费、SMTP 重试及保密边界。"""
import re
import smtplib
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.conf import settings
from django.core import mail
from django.db import transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.models import User, EmailChallenge
from apps.auth_app.recovery import challenge_code
from apps.core.models import OutboxEvent
from apps.core.tasks import dispatch_outbox, cleanup_expired_sessions
from apps.logs.models import OperationLog

BASE = '/api/v1/auth/'
PASSWORD = 'Member#12345'
NEW_PASSWORD = 'EntirelyFresh#839104!'


@pytest.fixture(autouse=True)
def email_settings():
    mail.outbox = []
    with override_settings(AUTH_EMAIL_ENABLED=True, EMAIL_HOST='localhost', DEFAULT_FROM_EMAIL='auth@example.com',
                           EMAIL_USE_TLS=False, EMAIL_USE_SSL=False, EMAIL_TIMEOUT=10,
                           EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
        yield


def verify_stored_email(user):
    user.verified_email = user.email.strip().casefold()
    user.save(update_fields=['verified_email'])


def request_reset(client, user):
    return client.post(BASE + 'recovery/request/', {'username': user.username, 'email': user.email}, format='json')


def latest_code():
    dispatch_outbox()
    assert mail.outbox
    return re.search(r'[0-9a-f]{32}\.[0-9a-f]{64}', mail.outbox[-1].body).group()


def reset(client, code, password=NEW_PASSWORD, confirmation=None):
    return client.post(BASE + 'recovery/reset/', {'code': code, 'new_password': password,
                       'new_password2': password if confirmation is None else confirmation}, format='json')


@pytest.mark.django_db
def test_public_configuration_ignores_bearer_and_no_store():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Bearer invalid')
    response = client.get(BASE + 'recovery/config/')
    assert response.status_code == 200
    assert response.data['data'] == {'enabled': True}
    assert response['Cache-Control'] == 'private, no-store'


@pytest.mark.django_db
def test_unknown_inactive_unverified_and_wrong_email_identical(member_user):
    client = APIClient()
    responses = []
    for username, email in [('unknown', member_user.email), (member_user.username, member_user.email)]:
        responses.append(client.post(BASE + 'recovery/request/', {'username': username, 'email': email}, format='json'))
    verify_stored_email(member_user)
    responses.append(client.post(BASE + 'recovery/request/', {'username': member_user.username, 'email': 'wrong@example.com'}, format='json'))
    member_user.is_active = False
    member_user.save(update_fields=['is_active'])
    responses.append(request_reset(client, member_user))
    assert all(response.status_code == 202 for response in responses)
    assert all(response.data == responses[0].data for response in responses)
    assert not EmailChallenge.objects.exists()
    assert not OutboxEvent.objects.exists()
    assert not mail.outbox


@pytest.mark.django_db
def test_verified_account_request_never_calls_smtp_or_broker(member_user):
    verify_stored_email(member_user)
    with patch('apps.core.events._dispatch_after_commit') as broker, patch('apps.auth_app.recovery.EmailMessage.send') as smtp:
        response = request_reset(APIClient(), member_user)
    assert response.status_code == 202
    broker.assert_not_called()
    smtp.assert_not_called()
    event = OutboxEvent.objects.get()
    challenge = EmailChallenge.objects.get()
    assert event.topic == 'auth.email'
    assert event.payload == {'challenge_id': str(challenge.pk)}
    assert challenge.expires_at - challenge.created_at <= timedelta(minutes=10)


@pytest.mark.django_db
def test_mail_is_paste_code_and_no_persistent_secret(member_user):
    verify_stored_email(member_user)
    request_reset(APIClient(), member_user)
    code = latest_code()
    assert len(code) == 97
    assert 'http' not in mail.outbox[0].body
    assert mail.outbox[0].to == [member_user.email]
    assert code not in str(EmailChallenge.objects.values().get())
    assert code not in str(OutboxEvent.objects.values().get())
    assert code not in str(list(OperationLog.objects.values()))
    assert dispatch_outbox() == {'processed': 0, 'failed': 0}
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_reset_changes_password_revokes_both_tokens_and_clears_initial_state(member_user, member_client):
    token_pair = APIClient().post(BASE + 'login/', {'username': member_user.username, 'password': PASSWORD}, format='json').data
    verify_stored_email(member_user)
    member_user.must_change_password = True
    member_user.save(update_fields=['must_change_password'])
    client = APIClient()
    request_reset(client, member_user)
    code = latest_code()
    response = reset(client, code)
    assert response.status_code == 200
    assert response.data['data'] is None
    member_user.refresh_from_db()
    assert member_user.check_password(NEW_PASSWORD)
    assert not member_user.must_change_password
    assert member_user.session_version == 1
    assert member_client.get(BASE + 'me/').status_code == 401
    assert client.post(BASE + 'refresh/', {'refresh': token_pair['refresh']}, format='json').status_code == 400
    assert reset(client, code).status_code == 400
    assert client.post(BASE + 'login/', {'username': member_user.username, 'password': NEW_PASSWORD}, format='json').status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('fault', ['expired', 'consumed', 'inactive', 'email', 'password', 'version', 'signature', 'purpose', 'secret'])
def test_reset_snapshot_tampering_and_expiry_are_generic(fault, member_user):
    verify_stored_email(member_user)
    client = APIClient()
    request_reset(client, member_user)
    challenge = EmailChallenge.objects.get()
    code = challenge_code(challenge)
    if fault == 'expired':
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
    elif fault == 'consumed':
        challenge.consumed_at = timezone.now()
    elif fault == 'purpose':
        challenge.purpose = 'verify'
    elif fault == 'inactive':
        member_user.is_active = False
        member_user.save(update_fields=['is_active'])
    elif fault == 'email':
        member_user.email = 'changed@example.com'
        member_user.save(update_fields=['email'])
    elif fault == 'password':
        member_user.set_password('Different#123456!')
        member_user.save(update_fields=['password'])
    elif fault == 'version':
        member_user.session_version += 1
        member_user.save(update_fields=['session_version'])
    elif fault == 'signature':
        code = code[:33] + '0' * 64
    challenge.save()
    with override_settings(SECRET_KEY='rotated-key' if fault == 'secret' else settings.SECRET_KEY):
        response = reset(client, code)
    assert response.status_code == 400
    assert response.data['data'] == {'code': ['确认凭据无效或已过期，请重新申请']}
    assert code not in str(response.data)


@pytest.mark.django_db
def test_new_request_invalidates_old_challenge(member_user):
    verify_stored_email(member_user)
    client = APIClient()
    request_reset(client, member_user)
    old = challenge_code(EmailChallenge.objects.get())
    request_reset(client, member_user)
    assert reset(client, old).status_code == 400
    assert dispatch_outbox() == {'processed': 2, 'failed': 0}
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_secret_rotation_terminates_queued_mail_without_reissuing_code(member_user):
    verify_stored_email(member_user)
    request_reset(APIClient(), member_user)
    with override_settings(SECRET_KEY='different-new-signing-key'):
        assert dispatch_outbox() == {'processed': 1, 'failed': 0}
    assert not mail.outbox


@pytest.mark.django_db
@pytest.mark.parametrize('password,confirmation,field', [(PASSWORD, None, 'new_password'), ('123', None, 'new_password'),
                                                       (NEW_PASSWORD, 'different', 'new_password2')])
def test_invalid_new_password_does_not_consume(password, confirmation, field, member_user):
    verify_stored_email(member_user)
    client = APIClient()
    request_reset(client, member_user)
    code = latest_code()
    response = reset(client, code, password, confirmation)
    assert response.status_code == 400
    assert field in response.data['data']
    assert EmailChallenge.objects.get().consumed_at is None
    assert reset(client, code).status_code == 200


@pytest.mark.django_db
def test_email_verification_requires_password_then_returns_profile(member_user, member_client):
    response = member_client.post(BASE + 'email-verification/request/', {'current_password': 'incorrect'}, format='json')
    assert response.status_code == 403
    assert not EmailChallenge.objects.exists()
    response = member_client.post(BASE + 'email-verification/request/', {'current_password': PASSWORD}, format='json')
    assert response.status_code == 202
    code = latest_code()
    response = member_client.post(BASE + 'email-verification/confirm/', {'code': code}, format='json')
    assert response.status_code == 200
    assert response.data['data']['email_verified'] is True
    assert response.data['data']['recovery_enabled'] is True
    member_user.refresh_from_db()
    assert member_user.verified_email == member_user.email
    assert member_client.post(BASE + 'email-verification/confirm/', {'code': code}, format='json').status_code == 400
    assert member_client.get(BASE + 'me/').data['data']['email_verified'] is True
    # 管理后台仅显示验证状态，不能经 readonly 原始地址绕过联系方式脱敏。
    user_admin = admin.site._registry[User]
    assert 'contact_verified' in user_admin.readonly_fields
    assert 'verified_email' not in str(user_admin.fieldsets)


@pytest.mark.django_db
def test_another_account_cannot_consume_verification(member_user, member_client, admin_client):
    member_client.post(BASE + 'email-verification/request/', {'current_password': PASSWORD}, format='json')
    code = latest_code()
    response = admin_client.post(BASE + 'email-verification/confirm/', {'code': code}, format='json')
    assert response.status_code == 400
    assert EmailChallenge.objects.get().consumed_at is None
    assert member_client.post(BASE + 'email-verification/confirm/', {'code': code}, format='json').status_code == 200


@pytest.mark.django_db
def test_email_change_clears_claim_and_challenges_even_if_changed_back(member_user, member_client):
    verify_stored_email(member_user)
    request_reset(APIClient(), member_user)
    old = member_user.email
    member_user.email = 'Changed@EXAMPLE.COM'
    member_user.save(update_fields=['email'])
    member_user.refresh_from_db()
    assert member_user.email == 'changed@example.com'
    assert member_user.verified_email is None
    assert EmailChallenge.objects.get().consumed_at is not None
    member_user.email = old
    member_user.save(update_fields=['email'])
    assert not member_user.email_verified
    other = User.objects.create_user('other', old, PASSWORD)
    verify_stored_email(other)
    assert other.email_verified


@pytest.mark.django_db
def test_stale_full_save_cannot_resurrect_old_email_claim(member_user):
    verify_stored_email(member_user)
    stale = User.objects.get(pk=member_user.pk)
    original = member_user.email
    member_user.email = 'different@example.com'
    member_user.save(update_fields=['email'])
    member_user.email = original
    member_user.save(update_fields=['email'])
    stale.first_name = 'new name'
    stale.save()
    stale.refresh_from_db()
    assert stale.verified_email is None


@pytest.mark.django_db
def test_profile_and_admin_user_write_revoke_claim(member_user, member_client, admin_client):
    verify_stored_email(member_user)
    response = member_client.patch(BASE + 'profile/', {'email': 'new@example.com', 'profile_version': member_user.profile_version}, format='json')
    assert response.status_code == 200
    member_user.refresh_from_db()
    assert member_user.verified_email is None
    verify_stored_email(member_user)
    assert admin_client.patch(f'/api/v1/users/{member_user.pk}/', {'email': 'last@example.com'}, format='json').status_code == 200
    member_user.refresh_from_db()
    assert member_user.verified_email is None


@pytest.mark.django_db
def test_only_one_account_can_claim_email(member_user, member_client, admin_user, admin_client):
    admin_user.email = member_user.email.upper()
    admin_user.save(update_fields=['email'])
    member_client.post(BASE + 'email-verification/request/', {'current_password': PASSWORD}, format='json')
    admin_client.post(BASE + 'email-verification/request/', {'current_password': 'Admin#12345'}, format='json')
    challenges = {challenge.user_id: challenge_code(challenge) for challenge in EmailChallenge.objects.all()}
    assert member_client.post(BASE + 'email-verification/confirm/', {'code': challenges[member_user.pk]}, format='json').status_code == 200
    assert admin_client.post(BASE + 'email-verification/confirm/', {'code': challenges[admin_user.pk]}, format='json').status_code == 400
    admin_user.refresh_from_db()
    assert admin_user.verified_email is None


@pytest.mark.django_db
def test_smtp_failure_sanitized_bounded_and_retry_succeeds(member_user):
    verify_stored_email(member_user)
    request_reset(APIClient(), member_user)
    with patch('apps.auth_app.recovery.EmailMessage.send', side_effect=smtplib.SMTPAuthenticationError(535, b'secret-smtp-password')):
        for _ in range(5):
            OutboxEvent.objects.update(available_at=timezone.now())
            assert dispatch_outbox() == {'processed': 0, 'failed': 1}
        OutboxEvent.objects.update(available_at=timezone.now())
        assert dispatch_outbox() == {'processed': 0, 'failed': 0}
    event = OutboxEvent.objects.get()
    assert event.attempts == 5
    assert event.last_error == 'SMTPAuthenticationError'
    assert 'secret-smtp-password' not in str(OutboxEvent.objects.values().get())
    assert EmailChallenge.objects.get().consumed_at is None
    request_reset(APIClient(), member_user)
    assert dispatch_outbox() == {'processed': 1, 'failed': 0}
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@pytest.mark.parametrize('state', ['inactive', 'consumed', 'expired', 'email', 'version'])
def test_dispatch_does_not_send_stale_binding(state, member_user):
    verify_stored_email(member_user)
    request_reset(APIClient(), member_user)
    if state == 'inactive':
        User.objects.filter(pk=member_user.pk).update(is_active=False)
    elif state == 'consumed':
        EmailChallenge.objects.update(consumed_at=timezone.now())
    elif state == 'expired':
        EmailChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    elif state == 'email':
        User.objects.filter(pk=member_user.pk).update(email='changed@example.com')
    else:
        User.objects.filter(pk=member_user.pk).update(session_version=1)
    assert dispatch_outbox() == {'processed': 1, 'failed': 0}
    assert not mail.outbox


@pytest.mark.django_db
def test_atomic_reset_rolls_back_password_and_consumption(member_user):
    verify_stored_email(member_user)
    client = APIClient()
    request_reset(client, member_user)
    code = latest_code()
    with patch('apps.auth_app.recovery.audit', side_effect=RuntimeError('audit failure')):
        response = reset(client, code)
    assert response.status_code == 500
    member_user.refresh_from_db()
    assert member_user.check_password(PASSWORD)
    assert EmailChallenge.objects.get().consumed_at is None


@pytest.mark.django_db
def test_rollback_does_not_leave_challenge_or_event(member_user):
    from apps.auth_app.recovery import create_challenge
    with pytest.raises(RuntimeError), transaction.atomic():
        create_challenge(member_user, 'verify', APIClient().request())
        raise RuntimeError('rollback')
    assert not EmailChallenge.objects.exists()
    assert not OutboxEvent.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize('settings_change', [{'AUTH_EMAIL_ENABLED': False}, {'ADMINCORE_MODULES': ()}])
def test_disabled_and_minimal_modes_fail_closed(settings_change, member_client):
    with override_settings(**settings_change):
        assert APIClient().get(BASE + 'recovery/config/').data['data'] == {'enabled': False}
        assert request_reset(APIClient(), User.objects.get(username='member')).status_code == 503
        assert reset(APIClient(), '0' * 32 + '.' + '0' * 64).status_code == 503
        assert member_client.post(BASE + 'email-verification/request/', {'current_password': PASSWORD}, format='json').status_code == 503
        assert member_client.get(BASE + 'profile/').data['data']['recovery_enabled'] is False
    assert not EmailChallenge.objects.exists()


@pytest.mark.django_db
def test_limits_and_cache_failure_are_closed(member_user):
    client = APIClient()
    with patch('apps.auth_app.recovery.time.time', return_value=600):
        for _ in range(5):
            assert request_reset(client, member_user).status_code == 202
        response = request_reset(client, member_user)
        assert response.status_code == 429
        assert response['Retry-After'] == '60'
    with patch('apps.auth_app.recovery.cache.add', side_effect=RuntimeError('private-redis-url')):
        response = client.post(BASE + 'recovery/request/', {'username': 'other', 'email': 'other@example.com'}, format='json')
    assert response.status_code == 503
    assert 'private-redis-url' not in str(response.data)


@pytest.mark.django_db
def test_strict_schema_size_limits_and_generic_code_errors(member_user):
    client = APIClient()
    assert client.post(BASE + 'recovery/request/', {'username': member_user.username, 'email': member_user.email, 'role': 'admin'}, format='json').status_code == 400
    response = reset(client, 'not-a-valid-code')
    assert response.status_code == 400
    assert response.data['data']['code'] == ['确认凭据无效或已过期，请重新申请']
    response = client.post(BASE + 'recovery/reset/', {'code': 'x' * 5000, 'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD}, format='json')
    assert response.status_code == 400
    assert 'x' * 5000 not in str(response.data)
    assert response['Cache-Control'] == 'private, no-store'


@pytest.mark.django_db
def test_retention_bounds_old_challenge_records(member_user):
    from apps.auth_app.recovery import create_challenge
    for _ in range(3):
        create_challenge(member_user, 'verify', APIClient().request())
    ids = list(EmailChallenge.objects.values_list('pk', flat=True))
    EmailChallenge.objects.filter(pk__in=ids[:2]).update(expires_at=timezone.now() - timedelta(days=31))
    assert cleanup_expired_sessions(batch_size=1)['deleted_email_challenges'] == 1
    assert cleanup_expired_sessions()['deleted_email_challenges'] == 1
    assert EmailChallenge.objects.count() == 1
