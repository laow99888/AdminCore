"""图形验证码不查询账户、SQL 门槛/一次消费、反绕过和保密边界。"""
import base64
import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.core.cache import cache
from django.db import OperationalError
from django.db.models.query import QuerySet
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APIRequestFactory

from apps.auth_app import login_captcha as captcha
from apps.auth_app.models import LoginCaptchaGuard, LoginCaptchaChallenge, AuthSession, TOTPDevice
from apps.auth_app.totp import hotp
from apps.core.tasks import cleanup_expired_sessions
from apps.logs.models import LoginLog

BASE = '/api/v1/auth/'
PASSWORD = 'Member#12345'
ANSWER = 'A3D7K'


@pytest.fixture(autouse=True)
def captcha_settings():
    with override_settings(AUTH_LOGIN_CAPTCHA_ENABLED=True, AUTH_LOGIN_CAPTCHA_FAILURE_THRESHOLD=3):
        yield


def request(username='member', ip='127.0.0.1'):
    return APIRequestFactory().post('/', {'username': username}, format='json', REMOTE_ADDR=ip)


def fail(username='member', count=3, ip='127.0.0.1'):
    for _ in range(count):
        captcha.record_failure(request(username, ip), username)


def challenge(client=None, username='member'):
    with patch('apps.auth_app.login_captcha.secrets.choice', side_effect=list(ANSWER)):
        response = (client or APIClient()).post(BASE + 'login-captcha/', {'username': username}, format='json')
    assert response.status_code == 200
    return response.data['data']


def login(data=None, client=None):
    payload = {'username': 'member', 'password': PASSWORD, **(data or {})}
    return (client or APIClient()).post(BASE + 'login/', payload, format='json')


def proof(data):
    return {'captcha_id': data['challenge_id'], 'captcha_code': ANSWER}


@pytest.mark.django_db
def test_disabled_does_not_create_security_rows(member_user):
    with override_settings(AUTH_LOGIN_CAPTCHA_ENABLED=False):
        fail()
        assert challenge() == {'required': False}
        assert login().status_code == 200
    assert not LoginCaptchaGuard.objects.exists()
    assert not LoginCaptchaChallenge.objects.exists()


@pytest.mark.django_db
def test_threshold_same_for_existing_unknown_and_normalized_usernames(member_user):
    assert challenge() == {'required': False}
    fail(' Member ', count=2)
    assert challenge(username='MEMBER') == {'required': False}
    fail('member', count=1)
    assert challenge(username='MEMBER')['required'] is True
    fail('unknown')
    assert challenge(username='unknown')['required'] is True
    assert LoginCaptchaChallenge.objects.count() == 2


@pytest.mark.django_db
def test_failure_window_is_fixed_and_expires(member_user):
    start = timezone.now()
    with patch('apps.auth_app.login_captcha.timezone.now', return_value=start):
        fail(count=1)
    pair, ip = captcha.identities(request(), 'member')
    first_expiry = LoginCaptchaGuard.objects.get(pk=pair).failure_expires_at
    with patch('apps.auth_app.login_captcha.timezone.now', return_value=start + timedelta(minutes=5)):
        fail(count=2)
    assert LoginCaptchaGuard.objects.get(pk=pair).failure_expires_at == first_expiry == start + timedelta(minutes=15)
    with patch('apps.auth_app.login_captcha.timezone.now', return_value=start + timedelta(minutes=15)):
        assert challenge() == {'required': False}


@pytest.mark.django_db
def test_ip_aggregate_stops_rotating_usernames_and_success_clears_only_pair(member_user):
    for i in range(10):
        fail('unknown' + str(i), count=1)
    data = challenge()
    assert data['required'] is True
    assert login(proof(data)).status_code == 200
    pair, ip = captcha.identities(request(), 'member')
    assert LoginCaptchaGuard.objects.get(pk=pair).failure_count == 0
    assert LoginCaptchaGuard.objects.get(pk=ip).failure_count == 10
    assert challenge()['required'] is True


@pytest.mark.django_db
def test_png_no_answer_metadata_or_secret_response(member_user):
    fail()
    data = challenge()
    assert set(data) == {'required', 'challenge_id', 'image', 'expires_in'}
    assert data['expires_in'] == 120
    assert data['image'].startswith('data:image/png;base64,')
    png = base64.b64decode(data['image'].split(',', 1)[1])
    with Image.open(io.BytesIO(png)) as image:
        assert image.format == 'PNG' and image.size == (180, 64) and not image.info
    assert len(data['image']) < 200_000
    assert ANSWER not in str(LoginCaptchaChallenge.objects.values().get())
    assert 'member' not in str(list(LoginCaptchaGuard.objects.values()))
    assert '127.0.0.1' not in str(list(LoginCaptchaGuard.objects.values()))


@pytest.mark.django_db
def test_missing_wrong_expired_and_consumed_errors_uniform(member_user):
    fail()
    response = login()
    assert response.status_code == 400 and response.data['data']['code'] == 'captcha_required'
    data = challenge()
    response = login({**proof(data), 'captcha_code': 'WRONG'})
    assert response.status_code == 400 and response.data['data']['code'] == 'captcha_invalid'
    response = login(proof(data))
    assert response.status_code == 400 and response.data['data']['code'] == 'captcha_invalid'
    data = challenge()
    LoginCaptchaChallenge.objects.filter(pk=data['challenge_id']).update(expires_at=timezone.now() - timedelta(seconds=1))
    response = login(proof(data))
    assert response.status_code == 400 and response.data['data']['code'] == 'captcha_invalid'
    assert LoginCaptchaChallenge.objects.get(pk=data['challenge_id']).consumed_at is not None
    assert not AuthSession.objects.exists()


@pytest.mark.django_db
def test_success_reset_does_not_allow_replay_same_submitted_captcha(member_user):
    fail()
    data = challenge()
    assert login(proof(data)).status_code == 200
    assert challenge() == {'required': False}
    response = login(proof(data))
    assert response.status_code == 400 and response.data['data']['code'] == 'captcha_invalid'
    assert AuthSession.objects.count() == 1


@pytest.mark.django_db
def test_wrong_password_still_consumes_proof(member_user):
    fail()
    data = challenge()
    assert login({**proof(data), 'password': 'wrong'}).status_code == 401
    assert LoginCaptchaChallenge.objects.get().consumed_at is not None
    assert login(proof(data)).status_code == 400


@pytest.mark.django_db
def test_cross_ip_and_username_binding_does_not_consume_victim(member_user):
    fail()
    data = challenge()
    fail('other')
    response = login({**proof(data), 'username': 'other'})
    assert response.status_code == 400 and response.data['data']['code'] == 'captcha_invalid'
    other_ip = APIClient(REMOTE_ADDR='127.0.0.2')
    fail(ip='127.0.0.2')
    assert login(proof(data), other_ip).status_code == 400
    assert LoginCaptchaChallenge.objects.get().consumed_at is None
    assert login(proof(data)).status_code == 200


@pytest.mark.django_db
def test_refresh_invalidates_previous_and_challenge_refresh_is_sql_limited(member_user):
    fail()
    first = challenge()
    second = challenge()
    assert LoginCaptchaChallenge.objects.get(pk=first['challenge_id']).consumed_at is not None
    assert login(proof(first)).status_code == 400
    assert login(proof(second)).status_code == 200
    cache.clear()  # SQL 限频不受本地/Redis计数清空影响。
    for _ in range(8):
        assert challenge() == {'required': False}
    response = APIClient().post(BASE + 'login-captcha/', {'username': 'rotated'}, format='json')
    assert response.status_code == 429
    assert response['Cache-Control'] == 'private, no-store'


@pytest.mark.django_db
def test_over_limit_new_username_does_not_allocate_more_guard_rows():
    for index in range(10):
        assert challenge(username='rotating' + str(index)) == {'required': False}
    count = LoginCaptchaGuard.objects.count()
    client = APIClient()
    for index in range(10, 20):
        response = client.post(BASE + 'login-captcha/', {'username': 'rotating' + str(index)}, format='json')
        assert response.status_code == 429
    assert LoginCaptchaGuard.objects.count() == count == 11


@pytest.mark.django_db
@pytest.mark.parametrize('bad', ['', 123, [], {}, 'A' * 100, None])
def test_malformed_code_consumed_or_missing_does_not_500(bad, member_user):
    fail()
    data = challenge()
    response = login({**proof(data), 'captcha_code': bad})
    assert response.status_code == 400
    assert response.data['data']['code'] == ('captcha_required' if bad is None else 'captcha_invalid')
    assert (LoginCaptchaChallenge.objects.get().consumed_at is not None) == (bad is not None)


@pytest.mark.django_db
def test_invalid_uuid_no_db_error(member_user):
    fail()
    response = login({'captcha_id': 'bad-uuid', 'captcha_code': ANSWER})
    assert response.status_code == 400 and response.data['data']['code'] == 'captcha_invalid'


@pytest.mark.django_db
def test_sql_and_cache_failures_are_closed_no_token(member_user):
    with patch('apps.auth_app.login_captcha.LoginCaptchaGuard.objects.select_for_update', side_effect=OperationalError('private-db-url')):
        response = login()
        assert response.status_code == 503
        assert 'private-db-url' not in str(response.data)
        assert APIClient().post(BASE + 'login-captcha/', {'username': 'member'}, format='json').status_code == 503
    with patch('apps.auth_app.throttling.cache.add', side_effect=RuntimeError('private-redis-url')):
        response = login()
        assert response.status_code == 503
        assert 'private-redis-url' not in str(response.data)
    assert not AuthSession.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize('operation', ['failure', 'challenge'])
def test_cleanup_winning_guard_lock_recreates_missing_row(operation):
    # 模拟清理先取得并删除过期行：删除发生在锁查询执行前，避免依赖 SQLite 行锁。
    old = timezone.now() - timedelta(days=2)
    pair, ip = captcha.identities(request(), 'member')
    for key in (pair, ip):
        LoginCaptchaGuard.objects.create(identity_digest=key, expires_at=old)
    original_get = QuerySet.get
    cleanup_won = []

    def get_after_cleanup(queryset, *args, **kwargs):
        if queryset.model is LoginCaptchaGuard and queryset.query.select_for_update and not cleanup_won:
            cleanup_won.append(True)
            LoginCaptchaGuard.objects.filter(expires_at__lte=old).delete()
        return original_get(queryset, *args, **kwargs)

    with patch.object(QuerySet, 'get', get_after_cleanup):
        if operation == 'failure':
            captcha.record_failure(request(), 'member')
        else:
            assert challenge() == {'required': False}
    assert cleanup_won
    assert LoginCaptchaGuard.objects.count() == 2
    assert not LoginCaptchaGuard.objects.filter(expires_at__lte=old).exists()
    assert LoginCaptchaGuard.objects.get(pk=pair).failure_count == (1 if operation == 'failure' else 0)


@pytest.mark.django_db
def test_success_guard_failure_rolls_back_session(member_user):
    with patch('apps.auth_app.login_captcha.record_success', side_effect=captcha.CaptchaUnavailable()):
        response = login()
    assert response.status_code == 503
    assert not AuthSession.objects.exists()
    assert not LoginLog.objects.filter(status='success').exists()


@pytest.mark.django_db
def test_image_error_rolls_back_challenge_without_logging_answer(member_user):
    fail()
    with patch('apps.auth_app.login_captcha.render_captcha', side_effect=RuntimeError('private image details')):
        response = APIClient().post(BASE + 'login-captcha/', {'username': 'member'}, format='json')
    assert response.status_code == 503
    assert 'private image details' not in str(response.data)
    assert not LoginCaptchaChallenge.objects.exists()


@pytest.mark.django_db
def test_existing_login_throttle_is_not_replaced(member_user):
    for _ in range(3):
        assert login({'password': 'wrong'}).status_code == 401
    data = challenge()
    assert login(proof(data)).status_code == 200
    assert login().status_code == 200
    assert login().status_code == 429


@pytest.mark.django_db
@pytest.mark.parametrize('username', ['member', 'unknown'])
def test_nth_failure_returns_immediate_captcha_prompt(username, member_user):
    for _ in range(2):
        response = login({'username': username, 'password': 'wrong'})
        assert response.status_code == 401
        assert not isinstance(response.data.get('data'), dict) or response.data['data'].get('code') != 'captcha_required'
    response = login({'username': username, 'password': 'wrong'})
    assert response.status_code == 401
    assert response.data['data']['code'] == 'captcha_required'
    assert LoginLog.objects.filter(username=username, status='failed').count() == 3
    assert login({'username': username, 'password': 'wrong'}).status_code == 400


@pytest.mark.django_db
def test_mfa_prompt_not_failure_and_invalid_factor_counts(member_user):
    key = Fernet.generate_key()
    secret = base64.b32encode(b'12345678901234567890').decode()
    TOTPDevice.objects.create(user=member_user, active_secret=Fernet(key).encrypt(secret.encode()).decode())
    with override_settings(AUTH_TOTP_ENCRYPTION_KEY=key.decode()):
        response = login()
        assert response.status_code == 401 and response.data['data']['code'] == 'mfa_required'
        assert not LoginCaptchaGuard.objects.filter(failure_count__gt=0).exists()
        assert login({'otp_code': '000000'}).status_code == 401
        pair, ip = captcha.identities(request(), 'member')
        assert LoginCaptchaGuard.objects.get(pk=pair).failure_count == 1
        fail(count=2)
        data = challenge()
        with patch('apps.auth_app.totp.time.time', return_value=30000):
            assert login({**proof(data), 'otp_code': hotp(secret, 1000)}).status_code == 200


@pytest.mark.django_db
def test_strict_json_and_malformed_login_boundaries(member_user):
    client = APIClient()
    assert client.post(BASE + 'login-captcha/', {'username': 'member'}).status_code == 415
    assert client.post(BASE + 'login-captcha/', {'username': 'member', 'answer': 'x'}, format='json').status_code == 400
    assert client.post(BASE + 'login-captcha/', {'username': 'a' * 2000}, format='json').status_code == 400
    for data in [[], {'username': []}, {'username': {'nested': 'invalid'}}, {'username': 'a' * 151}]:
        assert client.post(BASE + 'login/', data, format='json').status_code == 400
    assert not LoginLog.objects.exists()


@pytest.mark.django_db
def test_disabled_bearer_anonymous_and_no_store():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION='Bearer broken-token')
    response = client.post(BASE + 'login-captcha/', {'username': 'unknown'}, format='json')
    assert response.status_code == 200
    assert response.data['data'] == {'required': False}
    assert response['Cache-Control'] == 'private, no-store'


@pytest.mark.django_db
def test_maintenance_bounded_only_deletes_old_expired_security_rows(member_user):
    fail()
    data = challenge()
    old = timezone.now() - timedelta(days=2)
    old_keys = list(LoginCaptchaGuard.objects.values_list('pk', flat=True))
    LoginCaptchaGuard.objects.filter(pk__in=old_keys).update(expires_at=old)
    LoginCaptchaChallenge.objects.filter(pk=data['challenge_id']).update(expires_at=old)
    fail('new', ip='127.0.0.2')
    result = cleanup_expired_sessions(batch_size=1)
    assert result['deleted_login_captchas'] == 1 and result['deleted_captcha_guards'] == 1
    assert LoginCaptchaGuard.objects.filter(pk__in=old_keys).count() == 1
    result = cleanup_expired_sessions()
    assert result['deleted_captcha_guards'] == 1
    assert LoginCaptchaGuard.objects.exists()
