"""交叉审查新增问题的安全与契约回归。"""
import io
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import BaseThrottle
from drf_spectacular.generators import SchemaGenerator


@pytest.mark.parametrize('key', ['', 'your-secret-key-change-in-production',
                                  'django-insecure-' + 'x' * 64, 'x' * 64, 'short-key'])
def test_production_rejects_weak_secret(key):
    environment = os.environ.copy()
    environment.update(DJANGO_ENV='production', DJANGO_SETTINGS_MODULE='config.settings.production',
                       DB_PASSWORD='isolated-config-database-secret-012345', DJANGO_SECRET_KEY=key)
    process = subprocess.run([sys.executable, '-c', 'import config.settings.production'],
                             cwd=Path(__file__).resolve().parents[1], env=environment,
                             capture_output=True)
    assert process.returncode != 0
    assert b'ImproperlyConfigured' in process.stderr


def test_production_accepts_long_random_secret():
    environment = os.environ.copy()
    environment.update(DJANGO_ENV='production', DJANGO_SETTINGS_MODULE='config.settings.production',
                       DB_PASSWORD='isolated-config-database-secret-012345', DJANGO_SECRET_KEY='ABCdef0123456789_!-' * 4)
    process = subprocess.run([sys.executable, '-c', 'import config.settings.production'],
                             cwd=Path(__file__).resolve().parents[1], env=environment,
                             capture_output=True)
    assert process.returncode == 0


def test_forwarded_header_cannot_change_direct_client():
    factory = RequestFactory()
    throttle = BaseThrottle()
    with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'NUM_PROXIES': 0}):
        first = factory.get('/', REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_FOR='fake-a')
        second = factory.get('/', REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_FOR='fake-b')
        assert throttle.get_ident(first) == throttle.get_ident(second) == '192.0.2.1'
    with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}):
        first = factory.get('/', REMOTE_ADDR='172.18.0.2', HTTP_X_FORWARDED_FOR='fake-a,192.0.2.1')
        second = factory.get('/', REMOTE_ADDR='172.18.0.2', HTTP_X_FORWARDED_FOR='fake-b,192.0.2.1')
        assert throttle.get_ident(first) == throttle.get_ident(second) == '192.0.2.1'


@pytest.mark.django_db
def test_login_username_limit_across_source_addresses(monkeypatch):
    monkeypatch.setattr('apps.auth_app.throttling.time.time', lambda: 1_800_000_010.0)
    client = APIClient()
    for index in range(5):
        response = client.post('/api/v1/auth/login/', {'username': 'unknown', 'password': 'invalid'},
                               format='json', REMOTE_ADDR=f'192.0.2.{index}')
        assert response.status_code == 401
    response = client.post('/api/v1/auth/login/', {'username': 'unknown', 'password': 'invalid'},
                           format='json', REMOTE_ADDR='192.0.2.99')
    assert response.status_code == 429
    assert response.has_header('Retry-After')


@pytest.mark.django_db
def test_login_ip_limit_across_usernames(monkeypatch):
    clock = [1_800_000_010.0]
    monkeypatch.setattr('apps.auth_app.throttling.time.time', lambda: clock[0])
    client = APIClient()
    for index in range(10):
        assert client.post('/api/v1/auth/login/', {'username': f'unknown-{index}', 'password': 'invalid'},
                           format='json', HTTP_X_FORWARDED_FOR=f'forged-{index}').status_code == 401
    blocked = client.post('/api/v1/auth/login/', {'username': 'other', 'password': 'invalid'},
                          format='json', HTTP_X_FORWARDED_FOR='forged-last')
    assert blocked.status_code == 429 and blocked['Retry-After'] == '50'
    clock[0] += 60
    assert client.post('/api/v1/auth/login/', {'username': 'next-window', 'password': 'invalid'},
                       format='json', HTTP_X_FORWARDED_FOR='forged-next').status_code == 401


@pytest.mark.django_db
def test_registration_disabled_does_not_create_user(settings):
    from django.contrib.auth import get_user_model
    settings.ALLOW_PUBLIC_REGISTRATION = False
    response = APIClient().post('/api/v1/auth/register/', {'username': 'blocked-signup'}, format='json')
    assert response.status_code == 403
    assert not get_user_model().objects.filter(username='blocked-signup').exists()


@pytest.mark.django_db
def test_health_requires_database_and_redis(settings):
    settings.CACHES = {'default': {'BACKEND': 'django_redis.cache.RedisCache', 'LOCATION': 'redis://127.0.0.1:6379/0'}}
    client = APIClient()
    with patch('apps.core.diagnostics.Redis.from_url') as redis_connection:
        assert client.get('/api/v1/health/').status_code == 200
        redis_connection.return_value.ping.assert_called_once()
        redis_connection.return_value.ping.side_effect = ConnectionError('private connection details')
        response = client.get('/api/v1/health/')
        assert response.status_code == 503
        assert response.json() == {'status': 'unavailable'}
    with patch('django.db.connection.cursor', side_effect=ConnectionError('private database details')):
        assert client.get('/api/v1/health/').status_code == 503


@pytest.mark.django_db
def test_schema_requires_admin(admin_client, member_client):
    assert APIClient().get('/api/v1/schema/').status_code == 401
    assert member_client.get('/api/v1/schema/').status_code == 403
    assert admin_client.get('/api/v1/schema/').status_code == 200


@pytest.mark.django_db
def test_schema_strict_and_core_contracts():
    output = io.StringIO()
    call_command('spectacular', validate=True, fail_on_warn=True, stdout=output)
    schema = SchemaGenerator().get_schema(public=True)
    assert 'jwtAuth' in schema['components']['securitySchemes']
    paths = schema['paths']
    assert paths['/api/v1/auth/me/']['get']['security'] == [{'jwtAuth': []}]
    login = paths['/api/v1/auth/login/']['post']
    assert login.get('security', []) == []
    assert 'requestBody' in login
    assert paths['/api/v1/data-io/import/{task_id}/']['post']['operationId'] == 'data_io_import_retry'
    pagination = schema['components']['schemas']['PaginatedUserListList']['properties']
    assert set(pagination) == {'code', 'message', 'data'}
