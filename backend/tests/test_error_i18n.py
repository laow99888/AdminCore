"""API语言协商、错误边界与目录完整性；真实Nginx另由模板脚本验证。"""
import ast
import asyncio
import json
from pathlib import Path
from string import Formatter

import pytest
from django.http import JsonResponse, StreamingHttpResponse
from django.test import override_settings
from django.urls import path
from django.utils import translation
from rest_framework.exceptions import ValidationError, ErrorDetail
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.test import APIClient

from apps.core.error_i18n import ENGLISH, error_details, error_text
from apps.core.system_config import ConfigDefinition


class Messages(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        if request.query_params.get('mode') == 'error':
            raise ValidationError({'name': ['请求包含不允许的字段'], 'reason': 'captcha_required'})
        if request.query_params.get('mode') == 'plain':
            return JsonResponse({'code': 404, 'message': '模块未启用', 'data': {'title': '模块未启用'}}, status=404)
        if request.query_params.get('mode') == 'stream':
            return StreamingHttpResponse(iter([b'private']), content_type='text/event-stream')
        return Response({'code': 200, 'message': '创建成功', 'data': {'title': '创建成功', 'reason': 'captcha_required'}})


urlpatterns = [path('api/v1/i18n-fixture/', Messages.as_view())]


@pytest.mark.parametrize('header,language,message', [('', 'zh-hans', '参数验证失败'),
    ('en', 'en', 'Validation failed.'), ('en-US', 'en', 'Validation failed.'),
    ('zh-CN', 'zh-hans', '参数验证失败'), ('fr', 'zh-hans', '参数验证失败'),
    ('fr;q=1,en;q=0.5', 'en', 'Validation failed.')])
@override_settings(ROOT_URLCONF=__name__)
def test_negotiation_and_nested_validation_details(header, language, message):
    response = APIClient().get('/api/v1/i18n-fixture/?mode=error', HTTP_ACCEPT_LANGUAGE=header)
    assert response.status_code == 400 and response.json()['message'] == message
    assert response['Content-Language'] == language and 'Accept-Language' in response['Vary']
    data = response.json()['data']
    assert data['reason'] == 'captcha_required' and set(data) == {'name', 'reason'}
    assert data['name'] == (['The request contains unsupported fields.'] if language == 'en' else ['请求包含不允许的字段'])


@override_settings(ROOT_URLCONF=__name__)
def test_success_business_content_and_plain_json_are_separate():
    client = APIClient()
    success = client.get('/api/v1/i18n-fixture/', HTTP_ACCEPT_LANGUAGE='en').json()
    assert success['message'] == 'Created successfully.'
    assert success['data'] == {'title': '创建成功', 'reason': 'captcha_required'}
    error = client.get('/api/v1/i18n-fixture/?mode=plain', HTTP_ACCEPT_LANGUAGE='en')
    assert error.json()['message'] == 'The module is disabled.'
    assert error.json()['data'] == {'title': '模块未启用'}
    stream = client.get('/api/v1/i18n-fixture/?mode=stream', HTTP_ACCEPT_LANGUAGE='en')
    assert stream.streaming and b''.join(stream.streaming_content) == b'private'


def test_unknown_values_codes_and_error_types_are_preserved():
    with translation.override('en'):
        result = error_details({'x': ErrorDetail('请提供当前密码', code='required'),
            'title': '请提供当前密码', 'unknown': ErrorDetail('future_error', code='future')})
        assert result['x'] == 'Provide your current password.' and result['x'].code == 'required'
        assert result['title'] == '请提供当前密码' and result['unknown'].code == 'future'
        assert error_text('尚未登记的新消息') == '尚未登记的新消息'
        with pytest.raises(ValidationError) as exc:
            ConfigDefinition('test', 'test', 'integer', 2, minimum=1, maximum=5).validate(8)
        assert exc.value.detail['value'] == 'Must be an integer from 1 to 5.'


@pytest.mark.django_db
def test_builtin_errors_and_module_gate_use_language_without_changing_status(settings):
    client = APIClient()
    response = client.post('/api/v1/auth/login/', {}, format='json', HTTP_ACCEPT_LANGUAGE='en-US')
    assert response.status_code == 400
    assert response.json()['data']['username'] == ['This field is required.']
    settings.ADMINCORE_MODULES = ()
    response = client.get('/api/v1/files/', HTTP_ACCEPT_LANGUAGE='en')
    assert response.status_code == 404 and response.json()['message'] == 'The module is disabled.'
    assert response['Content-Language'] == 'en'


@pytest.mark.django_db
@pytest.mark.parametrize('language,message', [('en-US', 'The two passwords do not match.'), ('zh-CN', '两次输入的密码不一致')])
def test_password_mismatch_keeps_field_error_list(admin_client, language, message):
    response = admin_client.post('/api/v1/auth/change_password/', {
        'old_password': 'isolated-not-checked-for-mismatch', 'new_password': 'Isolated-strong-password!7',
        'new_password2': 'different-value'}, format='json', HTTP_ACCEPT_LANGUAGE=language)
    assert response.status_code == 400 and response.json()['data']['new_password'] == [message]


@pytest.mark.django_db
def test_replay_preserves_stored_result_and_business_title(admin_client, settings):
    from apps.core.models import IdempotencyRecord
    settings.ADMINCORE_MODULES = ('example',)
    settings.ROOT_URLCONF = 'tests.example_urls'
    headers = {'HTTP_IDEMPOTENCY_KEY': 'same-business-across-languages'}
    data = {'title': '创建成功', 'version': 0}
    first = admin_client.post('/api/v1/example/items/', data, format='json', HTTP_ACCEPT_LANGUAGE='zh-CN', **headers)
    assert first.status_code == 201
    before = json.loads(json.dumps(IdempotencyRecord.objects.get().response_data))
    repeated = admin_client.post('/api/v1/example/items/', data, format='json', HTTP_ACCEPT_LANGUAGE='en', **headers)
    assert repeated.status_code == 201 and repeated['Idempotency-Replayed'] == 'true'
    assert repeated.json()['data'] == first.json()['data'] and repeated.json()['data']['title'] == '创建成功'
    assert IdempotencyRecord.objects.get().response_data == before
    conflict = admin_client.post('/api/v1/example/items/', {'title': 'changed', 'version': 0}, format='json', HTTP_ACCEPT_LANGUAGE='en', **headers)
    assert conflict.status_code == 409 and conflict.json()['message'] == 'The same idempotency key cannot be used for different requests.'


def test_catalog_has_no_missing_static_server_messages_or_template_placeholders():
    assert ENGLISH and all(isinstance(key, str) and isinstance(value, str) and value.strip()
        and not any('\u4e00' <= char <= '\u9fff' for char in value) for key, value in ENGLISH.items())
    for key, value in ENGLISH.items():
        fields = lambda text: {field for _, field, _, _ in Formatter().parse(text) if field is not None}
        assert fields(key) == fields(value), key
    missing = set()
    sources = [ast.parse(file.read_text(encoding='utf-8-sig'))
               for file in (Path(__file__).parents[1] / 'apps').rglob('*.py') if 'migrations' not in file.parts]
    exception_names = {'APIException', 'ValidationError', 'PermissionDenied', 'AuthenticationFailed',
                       'NotFound', 'NotAuthenticated', 'Throttled', 'InvalidToken'}
    type_name = lambda node: node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ''
    previous = set()
    while previous != exception_names:
        previous = set(exception_names)
        for source in sources:
            for node in ast.walk(source):
                if isinstance(node, ast.ClassDef) and any(type_name(base) in exception_names for base in node.bases):
                    exception_names.add(node.name)
    for source in sources:
        for node in ast.walk(source):
            values = []
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                function = node.exc.func
                name = function.id if isinstance(function, ast.Name) else function.attr if isinstance(function, ast.Attribute) else ''
                if name in exception_names:
                    values = node.exc.args
            elif isinstance(node, ast.Dict):
                values = [value for key, value in zip(node.keys, node.values)
                          if isinstance(key, ast.Constant) and key.value == 'message']
            elif isinstance(node, ast.Assign) and any(isinstance(key, ast.Name) and key.id == 'default_detail' for key in node.targets):
                values = [node.value]
            def inspect(value):
                if isinstance(value, ast.JoinedStr):
                    if any(isinstance(part, ast.Constant) and isinstance(part.value, str)
                           and any('\u4e00' <= char <= '\u9fff' for char in part.value) for part in value.values):
                        missing.add('动态消息须使用error_text模板：' + ast.unparse(value))
                    return
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    if any('\u4e00' <= char <= '\u9fff' for char in value.value) and value.value not in ENGLISH:
                        missing.add(value.value)
                else:
                    for child in ast.iter_child_nodes(value):
                        inspect(child)
            for value in values:
                inspect(value)
    assert not missing, missing


def test_parallel_asgi_languages_do_not_leak():
    from config.realtime_asgi import application
    async def exercise():
        ready = asyncio.Event()
        count = 0
        async def one(language):
            output = []
            async def send(message):
                nonlocal count
                if message['type'] == 'http.response.start':
                    count += 1
                    if count == 2: ready.set()
                    await ready.wait()
                output.append(message)
            async def receive():
                return {'type': 'http.request'}
            await application({'type': 'http', 'method': 'GET', 'path': '/missing/', 'scheme': 'http',
                'headers': [(b'host', b'localhost'), (b'accept-language', language.encode())]}, receive, send)
            return output
        with translation.override('zh-hans'):
            english, chinese = await asyncio.wait_for(asyncio.gather(one('en-US'), one('zh-CN')), 2)
            assert translation.get_language() == 'zh-hans'
        assert json.loads(english[-1]['body'])['message'] == 'Not found.'
        assert json.loads(chinese[-1]['body'])['message'] == '未找到'
        assert dict(english[0]['headers'])[b'content-language'] == b'en'
        assert dict(chinese[0]['headers'])[b'content-language'] == b'zh-hans'
    asyncio.run(exercise())
