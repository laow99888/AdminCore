"""生命周期不可改变认证/业务正文/流；配置与发布窗口的反例检查。"""
import asyncio
from datetime import datetime, timezone
from io import BytesIO
import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.test import RequestFactory, override_settings
from django.urls import path
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from apps.core.api_lifecycle import (APILifecycleMiddleware, api_versions, load_configuration,
                                     parse_policies, response_headers)

PLAN = {'v1': {'deprecated_at': '2027-01-01T00:00:00Z', 'sunset_at': '2027-04-01T00:00:00Z',
               'migration_url': '/api/versions/'}}
PAST = {'v1': {**PLAN['v1'], 'deprecated_at': '2020-01-01T00:00:00Z', 'sunset_at': '2020-04-01T00:00:00Z'}}
urlpatterns = [path('api/v1/csrf-protected/', lambda request: HttpResponse('protected'))]


@pytest.mark.parametrize('raw', [None, [], True, {'v2': {}}, {'v1': []}, {'v1': {'unexpected': 1}},
    {'v1': {'sunset_at': '2027-04-01T00:00:00Z'}}, {'v1': {'deprecated_at': '2027-01-01T00:00:00Z'}},
    *({'v1': {**PLAN['v1'], 'deprecated_at': value}} for value in [None, 1, '2027-01-01', '2027-01-01T00:00:00+00:00', '2027-02-30T00:00:00Z', '1969-01-01T00:00:00Z']),
    *({'v1': {**PLAN['v1'], 'sunset_at': value}} for value in ['2026-01-01T00:00:00Z', '2027-03-31T23:59:59Z', '']),
    *({'v1': {**PLAN['v1'], 'migration_url': value}} for value in [None, '', 'http://example.com/', '//example.com/', '/unknown/', 'https://secret@example.com/', 'https://example.com/?token=secret', 'https://example.com/#secret', 'https://example.com:8443/', 'https://example.com/\r\nInjected:1', 'https://example.com/"', 'https://例子.test/'])])
def test_invalid_configuration_is_rejected_without_reflecting_input(raw):
    with pytest.raises(ImproperlyConfigured) as error:
        parse_policies(raw)
    assert 'secret' not in str(error.value) and 'Injected' not in str(error.value)


@pytest.mark.parametrize('raw', ['not-json', '[]', '{"v1":{},"v1":{}}', '{"v1":{"migration_url":"one","migration_url":"two"}}', ' ' * 4001])
def test_environment_json_rejects_duplicates_and_oversize(raw):
    with pytest.raises(ImproperlyConfigured):
        load_configuration(raw)


def test_boundaries_schedules_and_default_are_explicit():
    assert load_configuration('{}') == {}
    assert parse_policies({})['v1'].headers() == {'X-API-Version': 'v1'}
    policy = parse_policies(PLAN)['v1']
    assert policy.headers() == {'X-API-Version': 'v1', 'Deprecation': '@1798761600',
                                'Sunset': 'Thu, 01 Apr 2027 00:00:00 GMT', 'Link': '</api/versions/>; rel="deprecation"'}
    for date, status in [('2026-12-31', 'scheduled'), ('2027-01-01', 'deprecated'), ('2027-04-01', 'sunset_due')]:
        assert policy.describe(datetime.fromisoformat(date).replace(tzinfo=timezone.utc))['status'] == status
    no_sunset = {'v1': {'deprecated_at': PLAN['v1']['deprecated_at'], 'migration_url': 'https://docs.example.com/migrate-v1'}}
    assert 'Sunset' not in parse_policies(no_sunset)['v1'].headers()


@pytest.mark.parametrize('path,expected', [('/api/v1/health/', True), ('/api/v1/unknown/', True),
    ('/api/v2/health/', False), ('/api/v10/health/', False), ('/api/v1fake/health/', False),
    ('/admin/', False), ('/api/versions/', False), ('/static/file.js', False)])
def test_version_matching_does_not_label_other_surfaces(path, expected):
    assert bool(response_headers(path, parse_policies(PLAN))) is expected


@override_settings(ADMINCORE_API_LIFECYCLE=PLAN)
def test_middleware_preserves_error_body_status_cache_and_existing_links():
    response = HttpResponse(b'original error body', status=403, headers={'Cache-Control': 'private, no-store', 'Link': '</next>; rel="next"'})
    original = dict(response.headers)
    result = APILifecycleMiddleware(lambda request: response)(RequestFactory().get('/api/v1/users/'))
    assert result is response and result.content == b'original error body' and result.status_code == 403
    assert result['Cache-Control'] == original['Cache-Control']
    assert result['Link'] == '</next>; rel="next", </api/versions/>; rel="deprecation"'


@override_settings(ADMINCORE_API_LIFECYCLE=PLAN)
@pytest.mark.django_db
@pytest.mark.parametrize('kind', ['stream', 'file'])
def test_download_and_stream_are_not_consumed(kind):
    consumed = []
    def chunks():
        consumed.append(True)
        yield b'private-data'
    response = StreamingHttpResponse(chunks()) if kind == 'stream' else FileResponse(BytesIO(b'private-data'), as_attachment=True, filename='original.bin')
    original = response.streaming_content
    result = APILifecycleMiddleware(lambda request: response)(RequestFactory().get('/api/v1/files/one/download/'))
    assert not consumed and result.streaming and result['Deprecation'].startswith('@')
    assert b''.join(original) == b'private-data'
    if kind == 'file':
        assert 'original.bin' in result['Content-Disposition']
    result.close()


@override_settings(ADMINCORE_API_LIFECYCLE=PLAN)
def test_native_async_middleware():
    async def execute():
        async def view(request):
            return HttpResponse(b'async-original', status=202)
        result = await APILifecycleMiddleware(view)(RequestFactory().get('/api/v1/health/'))
        assert result.content == b'async-original' and result.status_code == 202 and result['X-API-Version'] == 'v1'
    asyncio.run(execute())


@override_settings(ADMINCORE_API_LIFECYCLE=PLAN)
@pytest.mark.django_db
def test_public_metadata_is_minimal_does_not_reflect_host_or_query(django_assert_num_queries):
    with django_assert_num_queries(0):
        response = api_versions(RequestFactory().get('/api/versions/?password=secret', HTTP_HOST='attacker.example'))
    data = json.loads(response.content)
    assert data['minimum_compatibility_days'] == 90 and data['automatic_retirement'] is False
    assert not any(value in response.content for value in [b'secret', b'attacker', b'user', b'database'])
    assert response['Cache-Control'] == 'no-store'
    assert api_versions(RequestFactory().post('/api/versions/')).status_code == 405


@pytest.mark.django_db
@override_settings(ADMINCORE_API_LIFECYCLE=PAST)
def test_expired_sunset_does_not_remove_authentication_or_business(admin_user):
    client = APIClient()
    assert client.get('/api/v1/users/').status_code == 401
    admin_client = APIClient()
    admin_client.force_authenticate(admin_user)
    response = admin_client.get('/api/v1/users/')
    assert response.status_code == 200 and response['Sunset'] == 'Wed, 01 Apr 2020 00:00:00 GMT'
    assert client.get('/api/versions/').json()['versions'][0]['status'] == 'sunset_due'
    assert client.get('/api/v1/no-such-route/')['X-API-Version'] == 'v1'
    assert 'X-API-Version' not in client.get('/api/v2/health/')


@pytest.mark.django_db
@override_settings(ADMINCORE_API_LIFECYCLE=PLAN, CORS_ALLOWED_ORIGINS=['https://client.example'])
def test_cors_exposes_lifecycle_without_allowing_other_origins():
    client = APIClient()
    good = client.get('/api/v1/health/', HTTP_ORIGIN='https://client.example')
    assert good['Access-Control-Allow-Origin'] == 'https://client.example'
    assert {'Deprecation', 'Sunset', 'Link', 'X-API-Version'} <= set(good['Access-Control-Expose-Headers'].split(', '))
    bad = client.get('/api/v1/health/', HTTP_ORIGIN='https://attacker.example')
    assert 'Access-Control-Allow-Origin' not in bad


@pytest.mark.django_db
@override_settings(ADMINCORE_API_LIFECYCLE=PLAN)
def test_early_csrf_and_https_redirects_keep_original_security_and_headers():
    from django.test import Client
    client = Client(enforce_csrf_checks=True)
    with override_settings(ROOT_URLCONF=__name__):
        response = client.post('/api/v1/csrf-protected/')
        assert response.status_code == 403 and response['X-API-Version'] == 'v1'
    with override_settings(SECURE_SSL_REDIRECT=True):
        response = Client().get('/api/v1/health/')
        assert response.status_code == 301 and response['Location'].startswith('https://')
        assert response['Deprecation'] == '@1798761600'


@pytest.mark.django_db
@pytest.mark.parametrize('config,deprecated', [(PLAN, False), (PAST, True), ({}, False)])
def test_generated_schema_matches_current_policy(config, deprecated):
    with override_settings(ADMINCORE_API_LIFECYCLE=config):
        result = SchemaGenerator().get_schema(public=True)
    operation = result['paths']['/api/v1/users/']['get']
    assert operation.get('deprecated', False) is deprecated
    assert operation['x-api-lifecycle']['version'] == 'v1'
    headers = operation['responses']['200']['headers']
    assert headers['X-API-Version']['example'] == 'v1'
    assert ('Deprecation' in headers) is bool(config)
    assert 'jwtAuth' in result['components']['securitySchemes']


@pytest.mark.django_db
@override_settings(ADMINCORE_API_LIFECYCLE=PLAN, ADMINCORE_MODULES=('realtime',))
def test_dedicated_sse_headers_match_on_stream_and_rejection():
    from tests.test_realtime import _asgi, scope
    for status, extra in [(200, {}), (405, {'method': 'POST'})]:
        output, _ = _asgi(scope(**extra), acquire='lease', snapshot={'notifications': {'total': 1}})
        assert output[0]['status'] == status
        headers = dict(output[0]['headers'])
        assert headers[b'deprecation'] == b'@1798761600'
        assert headers[b'sunset'] == b'Thu, 01 Apr 2027 00:00:00 GMT'
        assert headers[b'x-request-id']
