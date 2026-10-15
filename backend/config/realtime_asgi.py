"""专用 SSE ASGI 服务；普通 API 仍由原 WSGI 服务承载。"""
import asyncio
import json
import os
import re
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from asgiref.sync import sync_to_async
from django.db import connection, connections, transaction
from django.http import HttpRequest
from django.core.exceptions import DisallowedHost
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.core import realtime
from apps.core.modules import module_enabled
from apps.core.api_lifecycle import response_headers
from apps.core.error_i18n import error_text
from django.utils import translation

PATH = '/api/v1/realtime/events/'
SAFE_ID = re.compile(r'[A-Za-z0-9._:-]{1,100}\Z')


def _database(function, *args):
    try:
        with transaction.atomic():
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '3000ms'")
                    cursor.execute("SET LOCAL lock_timeout = '2000ms'")
                    cursor.execute("SET LOCAL transaction_timeout = '5000ms'")
            return function(*args)
    finally:
        # 流在等待期间不保留 DB 连接；同步查询在线程池里完成。
        connections.close_all()


async def database(function, *args):
    return await sync_to_async(_database, thread_sensitive=False)(function, *args)


def _headers(scope):
    result = {}
    for name, value in scope.get('headers', []):
        key = name.decode('ascii').lower()
        if key in result and key in {'authorization', 'host', 'origin', 'x-forwarded-proto'}:
            raise ValueError('重复请求头')
        result[key] = value.decode('latin1')
    return result


def _request(scope, headers):
    request = HttpRequest()
    request.META = {'HTTP_HOST': headers.get('host', ''),
                    'HTTP_X_FORWARDED_PROTO': headers.get('x-forwarded-proto', scope.get('scheme', 'http'))}
    host = request.get_host()
    scheme = 'https' if request.is_secure() else scope.get('scheme', 'http')
    if 'origin' in headers and headers['origin'] != f'{scheme}://{host}':
        raise ValueError('不允许跨源连接')
    authorization = headers.get('authorization', '')
    if not authorization.startswith('Bearer ') or not (1 <= len(authorization[7:]) <= 8192):
        return None
    return authorization[7:]


def _frame(event, value, sequence=None):
    prefix = f'id: {sequence}\n' if sequence is not None else ''
    return (prefix + f'event: {event}\ndata: ' + json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n\n').encode('utf-8')


async def _send(send, message):
    # 慢消费者也有界；客户端断线通过并发 receive 取消等待。
    await asyncio.wait_for(send(message), timeout=5)


async def _json(send, status, request_id):
    headers = [(b'content-type', b'application/json'), (b'cache-control', b'private, no-store'),
               (b'x-request-id', request_id.encode()), (b'x-content-type-options', b'nosniff'), (b'x-frame-options', b'DENY')]
    if status in {429, 503}:
        headers.append((b'retry-after', b'60'))
    await _send(send, {'type': 'http.response.start', 'status': status, 'headers': headers})
    await _send(send, {'type': 'http.response.body', 'body': json.dumps(
        {'code': status, 'message': error_text({400: '实时请求无效', 401: '登录凭据已失效', 403: '实时连接被拒绝',
         200: 'success', 404: '未找到', 405: '只允许 GET', 429: '实时连接达到上限', 503: '实时服务暂不可用'}.get(status, '服务暂不可用')),
         'data': None}).encode()})


async def _disconnect(receive):
    while True:
        message = await receive()
        if message['type'] == 'http.disconnect' or message.get('body'):
            return


async def _stream(raw_token, lease_id, request_id, send):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + realtime.STREAM_SECONDS
    previous = None
    sequence = 0
    while loop.time() < deadline:
        try:
            data = await asyncio.wait_for(database(realtime.snapshot, raw_token, lease_id),
                                          timeout=min(5, max(0.01, deadline - loop.time())))
        except (APIException, InvalidToken, TokenError):
            await _send(send, {'type': 'http.response.body', 'body': _frame('access_revoked', {'request_id': request_id}), 'more_body': True})
            break
        except Exception:
            await _send(send, {'type': 'http.response.body', 'body': _frame('unavailable', {'request_id': request_id}), 'more_body': True})
            break
        if previous != data:
            sequence += 1
            body = _frame('snapshot', {'request_id': request_id, 'topics': data}, sequence)
            previous = data
        else:
            body = b': heartbeat\n\n'
        await _send(send, {'type': 'http.response.body', 'body': body, 'more_body': True})
        await asyncio.sleep(min(realtime.POLL_SECONDS, max(0, deadline - loop.time())))
    await _send(send, {'type': 'http.response.body', 'body': b'', 'more_body': False})


async def application(scope, receive, send):
    if scope['type'] != 'http':
        return await localized_application(scope, receive, send)
    request = HttpRequest()
    request.META['HTTP_ACCEPT_LANGUAGE'] = ','.join(value.decode('latin1') for name, value
        in scope.get('headers', []) if name.lower() == b'accept-language')
    language = translation.get_language_from_request(request)
    async def localized_send(message):
        if message['type'] == 'http.response.start':
            message = {**message, 'headers': [*message.get('headers', []),
                (b'content-language', language.encode('ascii')), (b'vary', b'Accept-Language')]}
        await send(message)
    with translation.override(language):
        return await localized_application(scope, receive, localized_send)


async def localized_application(scope, receive, send):
    # 专用ASGI服务不经过Django中间件；仅装饰开始帧，不缓冲或消费事件流。
    original_send = send
    lifecycle = [(key.lower().encode('ascii'), value.encode('ascii'))
                 for key, value in response_headers(scope.get('path', '')).items()]
    async def send(message):
        if message['type'] == 'http.response.start' and lifecycle:
            message = {**message, 'headers': [*message.get('headers', []), *lifecycle]}
        await original_send(message)

    if scope['type'] == 'lifespan':
        while True:
            message = await receive()
            if message['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            elif message['type'] == 'lifespan.shutdown':
                await send({'type': 'lifespan.shutdown.complete'})
                return
    if scope['type'] != 'http':
        return
    request_id = uuid.uuid4().hex
    try:
        headers = _headers(scope)
        if SAFE_ID.fullmatch(headers.get('x-request-id', '')):
            request_id = headers['x-request-id']
        raw_token = _request(scope, headers)
    except (ValueError, UnicodeError, DisallowedHost):
        await _json(send, 400, request_id)
        return
    if scope.get('path') == '/health/':
        # 依赖就绪另由后端检查；此入口只检查此进程及模块启用。
        await _json(send, 200 if module_enabled('realtime') else 503, request_id)
        return
    if scope.get('path') != PATH or not module_enabled('realtime'):
        await _json(send, 404, request_id)
        return
    if scope['method'] != 'GET':
        await _json(send, 405, request_id)
        return
    if scope.get('query_string'):
        # 不允许 URL 携带令牌，也不接受任意订阅路径/对象 ID。
        await _json(send, 400, request_id)
        return
    if not raw_token:
        await _json(send, 401, request_id)
        return
    try:
        initial = await asyncio.wait_for(receive(), timeout=2)
    except TimeoutError:
        await _json(send, 400, request_id)
        return
    if initial['type'] == 'http.disconnect':
        return
    if initial['type'] != 'http.request' or initial.get('body') or initial.get('more_body'):
        await _json(send, 400, request_id)
        return
    lease_id = None
    tasks = []
    try:
        lease_id = await database(realtime.acquire, raw_token)
        await _send(send, {'type': 'http.response.start', 'status': 200, 'headers': [
            (b'content-type', b'text/event-stream; charset=utf-8'), (b'cache-control', b'private, no-store'),
            (b'x-accel-buffering', b'no'), (b'x-request-id', request_id.encode()),
            (b'x-content-type-options', b'nosniff'), (b'x-frame-options', b'DENY')]})
        tasks = [asyncio.create_task(_stream(raw_token, lease_id, request_id, send)),
                 asyncio.create_task(_disconnect(receive))]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (APIException, InvalidToken, TokenError) as exc:
        if lease_id is None:
            await _json(send, getattr(exc, 'status_code', 401), request_id)
    except (TimeoutError, ConnectionError, OSError):
        pass
    except Exception:
        if lease_id is None:
            await _json(send, 503, request_id)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if lease_id is not None:
            # 断线立即释放；进程强制退出有租约 TTL 兜底。
            await database(realtime.release, lease_id)
