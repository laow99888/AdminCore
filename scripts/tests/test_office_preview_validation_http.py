"""Long Office conversions must use the real rotating refresh flow, without bypassing revocation."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
SPEC = importlib.util.spec_from_file_location('office_validation_http', Path(__file__).parents[1] / 'validate_office_preview.py')
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


def response(status, data=None):
    return SimpleNamespace(status_code=status, json=lambda: data)


def client(monkeypatch, responses):
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return responses.pop(0)
    monkeypatch.setattr(validation.requests, 'request', request)
    def check(label, condition):
        if not condition:
            raise AssertionError(label)
    return validation.ValidationHTTP('http://127.0.0.1/api/v1/', check), calls


def test_expired_access_refreshes_rotating_pair_and_retries_same_upload(monkeypatch):
    http, calls = client(monkeypatch, [response(401), response(200, {'data': {
        'access': 'new-access', 'refresh': 'new-refresh'}}), response(201), response(200)])
    member = {'access': 'expired-access', 'refresh': 'old-refresh'}
    files = {'file': ('fixture.odt', b'private fixture bytes', 'application/octet-stream')}
    http('files/', token=member, method='POST', expected=201, files=files, key='same-key')
    http('files/', token=member)
    assert member == {'access': 'new-access', 'refresh': 'new-refresh'}
    assert calls[1][1].endswith('/auth/refresh/')
    assert calls[1][2]['json'] == {'refresh': 'old-refresh'}
    assert calls[1][2].get('headers', {}) == {}
    assert calls[0][2]['headers'] == {'Authorization': 'Bearer expired-access', 'Idempotency-Key': 'same-key'}
    assert calls[2][2]['headers'] == {'Authorization': 'Bearer new-access', 'Idempotency-Key': 'same-key'}
    assert calls[2][2]['files'] == files
    assert calls[3][2]['headers'] == {'Authorization': 'Bearer new-access'}


@pytest.mark.parametrize('status', [400, 401, 403, 429, 500])
def test_refresh_failure_never_logs_in_or_retries_business(monkeypatch, status):
    http, calls = client(monkeypatch, [response(401), response(status)])
    token = {'access': 'old', 'refresh': 'revoked'}
    with pytest.raises(AssertionError, match='refresh'):
        http('files/', token=token, method='POST', expected=201)
    assert len(calls) == 2 and token == {'access': 'old', 'refresh': 'revoked'}
    assert not any('/login/' in call[1] for call in calls)


@pytest.mark.parametrize('status', [403, 409, 429, 500])
def test_business_errors_are_never_retried(monkeypatch, status):
    http, calls = client(monkeypatch, [response(status)])
    with pytest.raises(AssertionError):
        http('files/', token={'access': 'active', 'refresh': 'valid'}, method='POST', expected=201)
    assert len(calls) == 1


def test_retry_is_bounded_and_does_not_hide_rejected_replacement(monkeypatch):
    http, calls = client(monkeypatch, [response(401), response(200, {'data': {
        'access': 'new', 'refresh': 'rotated'}}), response(401)])
    with pytest.raises(AssertionError):
        http('files/', token={'access': 'expired', 'refresh': 'valid'}, expected=201)
    assert len(calls) == 3


def test_expected_unauthorized_is_not_refreshed(monkeypatch):
    http, calls = client(monkeypatch, [response(401), response(401)])
    http('files/', expected=401)
    http('files/', token={'access': 'revoked', 'refresh': 'revoked'}, expected=401)
    assert len(calls) == 2


def test_login_retains_both_tokens_for_later_refresh(monkeypatch):
    http, calls = client(monkeypatch, [response(200, {'access': 'access', 'refresh': 'refresh'})])
    assert http.login('fixture-user', 'fixture-password') == {'access': 'access', 'refresh': 'refresh'}
    assert calls[0][2]['json'] == {'username': 'fixture-user', 'password': 'fixture-password'}


def test_second_expiry_uses_latest_refresh_not_consumed_original(monkeypatch):
    http, calls = client(monkeypatch, [response(401), response(200, {'data': {
        'access': 'access-2', 'refresh': 'refresh-2'}}), response(200), response(401),
        response(200, {'data': {'access': 'access-3', 'refresh': 'refresh-3'}}), response(200)])
    token = {'access': 'access-1', 'refresh': 'refresh-1'}
    http('files/', token=token)
    http('files/', token=token)
    assert calls[4][2]['json'] == {'refresh': 'refresh-2'}
    assert token == {'access': 'access-3', 'refresh': 'refresh-3'}


@pytest.mark.parametrize('pair', [{}, {'access': 'secret-access'}, {'access': '', 'refresh': 'secret-refresh'}, []])
def test_malformed_refresh_never_retries_or_leaks_pair(monkeypatch, pair, capsys):
    http, calls = client(monkeypatch, [response(401), response(200, {'data': pair})])
    token = {'access': 'secret-original', 'refresh': 'secret-original-refresh'}
    with pytest.raises(AssertionError) as exception:
        http('files/', token=token)
    assert len(calls) == 2
    assert token == {'access': 'secret-original', 'refresh': 'secret-original-refresh'}
    assert 'secret' not in str(exception.value) + capsys.readouterr().out
