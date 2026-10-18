"""凭证轮换和调用计数需要真实 PostgreSQL 行锁验证。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.api_credentials.models import APICredential, CredentialUsageDay
from tests.test_api_credentials import (BASE, PASSWORD, enable_api_credentials, issued,
                                        owner, session_client, token_client)  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def postgres():
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实PostgreSQL凭证行锁')


def parallel(count, operation):
    barrier = Barrier(count)
    def run(index):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            return operation(index)
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(run, range(count)))


def test_parallel_requests_count_once_without_lost_updates(session_client):
    postgres()
    data, _ = issued(session_client)
    assert parallel(8, lambda _: token_client(data['token']).get(BASE + 'tasks/').status_code) == [200] * 8
    row = APICredential.objects.get(pk=data['id'])
    assert row.accepted_requests == row.usage_count == 8
    assert CredentialUsageDay.objects.get(credential=row, day=timezone.now().date()).requests == 8


def test_parallel_rotation_only_one_secret_wins(session_client):
    postgres()
    data, old = issued(session_client)
    authorization = session_client._credentials['HTTP_AUTHORIZATION']
    def rotate(_):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=authorization)
        response = client.post(BASE + f'credentials/{data["id"]}/rotate/',
            {'version': 1, 'current_password': PASSWORD}, format='json')
        return response.status_code, response.json().get('data')
    results = parallel(2, rotate)
    assert sorted(status for status, _ in results) == [200, 409]
    token = next(body['token'] for status, body in results if status == 200)
    assert old.get(BASE + 'tasks/').status_code == 401
    assert token_client(token).get(BASE + 'tasks/').status_code == 200
    assert APICredential.objects.get(pk=data['id']).version == 2


def test_rotation_racing_old_auth_never_accepts_old_secret_after_completion(session_client):
    postgres()
    data, _ = issued(session_client)
    authorization = session_client._credentials['HTTP_AUTHORIZATION']
    def operation(index):
        if index:
            return token_client(data['token']).get(BASE + 'tasks/').status_code
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=authorization)
        return client.post(BASE + f'credentials/{data["id"]}/rotate/',
            {'version': 1, 'current_password': PASSWORD}, format='json').status_code
    outcomes = parallel(2, operation)
    assert outcomes[0] == 200 and outcomes[1] in (200, 401)
    assert token_client(data['token']).get(BASE + 'tasks/').status_code == 401
    row = APICredential.objects.get(pk=data['id'])
    assert row.accepted_requests == int(outcomes[1] == 200)
