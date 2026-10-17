"""仅供隔离代理回归：响应结束后模拟 ASGI 租约收尾，不读取数据库或凭据。"""
import asyncio


async def application(scope, receive, send):
    if scope['type'] != 'http':
        return
    await receive()
    await send({'type': 'http.response.start', 'status': 200,
                'headers': [(b'content-type', b'text/plain'), (b'cache-control', b'private, no-store')]})
    await send({'type': 'http.response.body', 'body': b'isolated-sse-protocol', 'more_body': False})
    # 必须在协议已结束、应用尚未返回的窗口复用连接，才能稳定暴露问题。
    if scope['path'] == '/api/v1/realtime/events/':
        await asyncio.sleep(.3)
