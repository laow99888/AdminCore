"""TOTP 的 RFC 向量、证明消费、加密、锁内回滚和密码单因素绕过边界。"""
import base64
import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.core import mail
from django.core.management import call_command, CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.models import TOTPDevice, AuthSession, EmailChallenge
from apps.auth_app.totp import hotp, recovery_hash
from apps.auth_app.recovery import challenge_code
from apps.logs.models import OperationLog

BASE = '/api/v1/auth/'
PASSWORD = 'Member#12345'


@pytest.fixture(autouse=True)
def totp_key():
    with override_settings(AUTH_TOTP_ENCRYPTION_KEY=Fernet.generate_key().decode()):
        yield


def post(client, operation, otp_code=None, password=PASSWORD):
    payload = {'current_password': password}
    if otp_code is not None:
        payload['otp_code'] = otp_code
    return client.post(BASE + 'totp/' + operation + '/', payload, format='json')


def enroll(client):
    response = post(client, 'setup')
    assert response.status_code == 200
    secret = response.data['data']['secret']
    code = hotp(secret, 1000)
    with patch('apps.auth_app.totp.time.time', return_value=30000):
        response = post(client, 'enable', code)
    assert response.status_code == 200
    result = response.data['data']
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + result['access'])
    return secret, result


def login(otp_code=None, password=PASSWORD):
    payload = {'username': 'member', 'password': password}
    if otp_code is not None:
        payload['otp_code'] = otp_code
    return APIClient().post(BASE + 'login/', payload, format='json')


@pytest.mark.parametrize('timestamp,expected', [(59, '94287082'), (1111111109, '07081804'),
    (1111111111, '14050471'), (1234567890, '89005924'), (2000000000, '69279037'), (20000000000, '65353130')])
def test_rfc6238_sha1_vectors(timestamp, expected):
    secret = base64.b32encode(b'12345678901234567890').decode()
    assert hotp(secret, timestamp // 30, digits=8) == expected
    assert hotp(secret, timestamp // 30) == expected[-6:]


@pytest.mark.django_db
def test_setup_stores_only_ciphertext_and_requires_password(member_user, member_client):
    assert post(member_client, 'setup', password='wrong').status_code == 403
    assert not TOTPDevice.objects.exists()
    response = post(member_client, 'setup')
    assert response.status_code == 200
    data = response.data['data']
    device = TOTPDevice.objects.get()
    assert data['secret'] not in device.pending_secret
    assert 'otpauth://totp/AdminCore%3Amember?' in data['otpauth_uri']
    assert device.pending_session_id == AuthSession.objects.get().pk
    assert device.pending_expires_at > timezone.now()
    assert device.pending_expires_at <= timezone.now() + timedelta(minutes=10)
    assert data['secret'] not in str(list(OperationLog.objects.values()))
    assert member_client.get(BASE + 'totp/').data['data'] == {
        'enabled': False, 'available': True, 'recovery_codes_remaining': 0}
    assert response['Cache-Control'] == 'private, no-store'


@pytest.mark.django_db
def test_repeated_setup_replaces_pending_secret(member_client):
    old = post(member_client, 'setup').data['data']['secret']
    new = post(member_client, 'setup').data['data']['secret']
    assert old != new
    with patch('apps.auth_app.totp.time.time', return_value=30000):
        assert post(member_client, 'enable', hotp(old, 1000)).status_code == 401
        assert post(member_client, 'enable', hotp(new, 1000)).status_code == 200


@pytest.mark.django_db
def test_enable_revokes_old_sessions_returns_once_codes(member_user, member_client):
    old_client = APIClient()
    old_client.credentials(HTTP_AUTHORIZATION=member_client._credentials['HTTP_AUTHORIZATION'])
    secret, data = enroll(member_client)
    device = TOTPDevice.objects.get()
    assert secret not in device.active_secret
    assert not device.pending_secret
    assert len(data['recovery_codes']) == 10
    assert len(set(data['recovery_codes'])) == 10
    assert all(len(code) == 32 for code in data['recovery_codes'])
    assert device.recovery_hashes == [recovery_hash(code) for code in data['recovery_codes']]
    assert old_client.get(BASE + 'me/').status_code == 401
    member_user.refresh_from_db()
    assert member_user.session_version == 1
    status = member_client.get(BASE + 'totp/')
    assert status.data['data'] == {'enabled': True, 'available': True, 'recovery_codes_remaining': 10}
    assert not set(data['recovery_codes']) & set(str(status.data).split())
    assert post(member_client, 'setup').status_code == 400


@pytest.mark.django_db
def test_login_requires_second_factor_and_consumes_counter(member_client):
    secret, data = enroll(member_client)
    before = AuthSession.objects.count()
    response = login()
    assert response.status_code == 401
    assert response.data['data']['code'] == 'mfa_required'
    assert AuthSession.objects.count() == before
    assert login('000000').status_code == 401
    with patch('apps.auth_app.totp.time.time', return_value=30030):
        code = hotp(secret, 1001)
        response = login(code)
        assert response.status_code == 200
        assert login(code).status_code == 401
    assert TOTPDevice.objects.get().last_counter == 1001


@pytest.mark.django_db
@pytest.mark.parametrize('offset', [-1, 0, 1, 2])
def test_step_window(offset, member_client):
    secret, _ = enroll(member_client)
    with patch('apps.auth_app.totp.time.time', return_value=30120):
        response = login(hotp(secret, 1004 + offset))
    assert response.status_code == (200 if offset <= 1 else 401)


@pytest.mark.django_db
def test_recovery_code_one_use_and_never_plaintext_stored(member_client):
    secret, data = enroll(member_client)
    code = data['recovery_codes'][0]
    assert login(code).status_code == 200
    assert login(code).status_code == 401
    assert len(TOTPDevice.objects.get().recovery_hashes) == 9
    assert code not in str(list(TOTPDevice.objects.values()))
    assert code not in str(list(OperationLog.objects.values()))


@pytest.mark.django_db
def test_regenerate_and_disable_require_proof_and_revoke_old_codes(member_client):
    secret, data = enroll(member_client)
    old_codes = data['recovery_codes']
    assert post(member_client, 'recovery-codes', '000000').status_code == 401
    response = post(member_client, 'recovery-codes', old_codes[0])
    assert response.status_code == 200
    data = response.data['data']
    assert member_client.get(BASE + 'me/').status_code == 401
    member_client.credentials(HTTP_AUTHORIZATION='Bearer ' + data['access'])
    assert login(old_codes[1]).status_code == 401
    response = post(member_client, 'disable', data['recovery_codes'][0])
    assert response.status_code == 200
    assert 'recovery_codes' not in response.data['data']
    assert member_client.get(BASE + 'me/').status_code == 401
    member_client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['data']['access'])
    device = TOTPDevice.objects.get()
    assert device.active_secret == '' and device.recovery_hashes == []
    assert login().status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('fault', ['expiry', 'session', 'password', 'version'])
def test_pending_snapshot_binding(fault, member_user, member_client):
    data = post(member_client, 'setup').data['data']
    device = TOTPDevice.objects.get()
    if fault == 'expiry':
        device.pending_expires_at = timezone.now() - timedelta(seconds=1)
    elif fault == 'session':
        device.pending_session_id = None
    elif fault == 'password':
        device.pending_password_digest = '0' * 64
    else:
        device.pending_session_version = 123
    device.save()
    with patch('apps.auth_app.totp.time.time', return_value=30000):
        assert post(member_client, 'enable', hotp(data['secret'], 1000)).status_code == 400
    assert not TOTPDevice.objects.get().active_secret


@pytest.mark.django_db
def test_another_valid_device_cannot_enable_pending(member_client):
    secret = post(member_client, 'setup').data['data']['secret']
    data = login().data
    other = APIClient()
    other.credentials(HTTP_AUTHORIZATION='Bearer ' + data['access'])
    with patch('apps.auth_app.totp.time.time', return_value=30000):
        assert post(other, 'enable', hotp(secret, 1000)).status_code == 400


@pytest.mark.django_db
def test_key_missing_or_changed_fail_closed(member_client):
    secret, data = enroll(member_client)
    for key in ['', Fernet.generate_key().decode()]:
        with override_settings(AUTH_TOTP_ENCRYPTION_KEY=key):
            assert login(data['recovery_codes'][0]).status_code == 503
            assert post(member_client, 'disable', data['recovery_codes'][0]).status_code == 503
    assert len(TOTPDevice.objects.get().recovery_hashes) == 10


@pytest.mark.django_db
def test_unconfigured_does_not_block_unenrolled_login(member_client):
    with override_settings(AUTH_TOTP_ENCRYPTION_KEY=''):
        assert login().status_code == 200
        assert post(member_client, 'setup').status_code == 503
        assert member_client.get(BASE + 'totp/').data['data']['available'] is False
    assert not TOTPDevice.objects.exists()


@pytest.mark.django_db
def test_email_reset_preserves_active_factor_and_clears_pending(member_user, member_client):
    secret, data = enroll(member_client)
    member_user.refresh_from_db()
    member_user.verified_email = member_user.email
    member_user.save(update_fields=['verified_email'])
    with override_settings(AUTH_EMAIL_ENABLED=True, EMAIL_HOST='localhost', DEFAULT_FROM_EMAIL='auth@example.com'):
        client = APIClient()
        response = client.post(BASE + 'recovery/request/', {'username': member_user.username, 'email': member_user.email}, format='json')
        assert response.status_code == 202
        code = challenge_code(EmailChallenge.objects.get())
        new = 'NewTotally#234578!'
        assert client.post(BASE + 'recovery/reset/', {'code': code, 'new_password': new, 'new_password2': new}, format='json').status_code == 200
    assert TOTPDevice.objects.get().active_secret
    assert login(password=new).data['data']['code'] == 'mfa_required'
    assert login(data['recovery_codes'][0], password=new).status_code == 200


@pytest.mark.django_db
def test_login_transaction_rolls_back_proof_if_issue_fails(member_client):
    secret, data = enroll(member_client)
    code = data['recovery_codes'][0]
    with patch('apps.auth_app.sessions.issue_session', side_effect=RuntimeError('failed')):
        assert login(code).status_code == 500
    assert recovery_hash(code) in TOTPDevice.objects.get().recovery_hashes
    assert login(code).status_code == 200


@pytest.mark.django_db
def test_enable_transaction_rolls_back_on_audit_failure(member_client):
    secret = post(member_client, 'setup').data['data']['secret']
    with patch('apps.auth_app.totp.audit', side_effect=RuntimeError('failed')), patch('apps.auth_app.totp.time.time', return_value=30000):
        assert post(member_client, 'enable', hotp(secret, 1000)).status_code == 500
    device = TOTPDevice.objects.get()
    assert not device.active_secret and device.last_counter == -1
    assert member_client.get(BASE + 'me/').status_code == 200


@pytest.mark.django_db
def test_admin_password_login_and_existing_session_cannot_bypass(admin_user):
    from django.test import Client
    client = Client()
    client.force_login(admin_user)
    assert client.get('/admin/').status_code == 200
    TOTPDevice.objects.create(user=admin_user, active_secret=Fernet(settings.AUTH_TOTP_ENCRYPTION_KEY.encode()).encrypt(b'A' * 32).decode())
    assert client.get('/admin/').status_code == 403
    client.logout()
    response = client.post('/admin/login/', {'username': admin_user.username, 'password': 'Admin#12345', 'next': '/admin/'})
    assert response.status_code == 200
    assert '_auth_user_id' not in client.session


@pytest.mark.django_db
def test_strict_schema_json_size_nostore(member_client):
    assert member_client.post(BASE + 'totp/setup/', {'current_password': PASSWORD, 'user': 'other'}, format='json').status_code == 400
    assert member_client.post(BASE + 'totp/setup/', {'current_password': PASSWORD}).status_code == 415
    response = member_client.post(BASE + 'totp/setup/', {'current_password': 'a' * 5000}, format='json')
    assert response.status_code == 400
    assert response['Cache-Control'] == 'private, no-store'


@pytest.mark.django_db
def test_wrong_proof_throttle_cache_failure_no_secret(member_client):
    secret, data = enroll(member_client)
    with patch('apps.auth_app.totp.time.time', return_value=30060):
        for _ in range(5):
            assert post(member_client, 'disable', '000000').status_code == 401
        assert post(member_client, 'disable', data['recovery_codes'][0]).status_code == 429
    with patch('apps.auth_app.recovery.cache.add', side_effect=RuntimeError('private redis detail')):
        response = post(member_client, 'disable', data['recovery_codes'][0])
    assert response.status_code == 503
    assert 'private redis detail' not in str(response.data)


@pytest.mark.django_db
def test_offline_recovery_requires_exact_confirmation_and_audit_reason(member_client, member_user):
    secret, data = enroll(member_client)
    for options in [{}, {'confirm_username': 'other', 'reason': 'lost device'},
                    {'confirm_username': 'member', 'reason': ''},
                    {'confirm_username': 'member', 'reason': 'a' * 201}]:
        with pytest.raises(CommandError):
            call_command('recover_totp', 'member', stdout=io.StringIO(), **options)
        assert TOTPDevice.objects.get().active_secret
        assert member_client.get(BASE + 'me/').status_code == 200
    output = io.StringIO()
    with override_settings(AUTH_TOTP_ENCRYPTION_KEY=''):
        call_command('recover_totp', 'member', confirm_username='member', reason='lost device confirmed by operator', stdout=output)
    device = TOTPDevice.objects.get()
    assert not device.active_secret and not device.pending_secret and not device.recovery_hashes
    assert member_client.get(BASE + 'me/').status_code == 401
    assert login().status_code == 200
    audit = OperationLog.objects.get(resource='totp', description__startswith='offline_totp_recovery')
    assert audit.user_id is None
    assert audit.resource_id == str(member_user.pk)
    assert audit.description == 'offline_totp_recovery; target=member; reason=lost device confirmed by operator'
    assert secret not in output.getvalue()
    assert all(code not in output.getvalue() for code in data['recovery_codes'])


@pytest.mark.django_db
def test_form_login_requires_factor_and_rejects_repeated_fields(member_client):
    from django.test import Client
    secret, data = enroll(member_client)
    client = Client()
    response = client.post(BASE + 'login/', {'username': 'member', 'password': PASSWORD})
    assert response.status_code == 401
    assert response.json()['data']['code'] == 'mfa_required'
    assert client.post(BASE + 'login/', {'username': 'member', 'password': PASSWORD,
        'otp_code': data['recovery_codes'][0]}).status_code == 200
    response = client.post(BASE + 'login/', 'username=member&password=one&password=two&otp_code=123456',
                           content_type='application/x-www-form-urlencoded')
    assert response.status_code == 400
