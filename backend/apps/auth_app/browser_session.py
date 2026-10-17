"""显式协商的浏览器刷新凭据传输；普通 API 仍只接受 Bearer。"""
from django.conf import settings
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework_simplejwt.tokens import UntypedToken

COOKIE_NAME = '__Host-admincore_refresh'
DEV_COOKIE_NAME = 'admincore_refresh_dev'
COOKIE_PATH = '/'  # __Host- 必须 Secure、Path=/ 且没有 Domain。


def refresh_cookie_name():
    return COOKIE_NAME if settings.SESSION_COOKIE_SECURE else DEV_COOKIE_NAME


def require_browser_transport(request):
    if not settings.AUTH_BROWSER_COOKIE_ENABLED:
        raise NotFound()
    if not settings.DEBUG and (not settings.SESSION_COOKIE_SECURE or not request.is_secure()):
        raise PermissionDenied('浏览器会话需要 HTTPS')
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return
    raw = request._request
    # 不将 CSRF_TRUSTED_ORIGINS 解释为允许跨域读取/改写浏览器会话。
    if raw.headers.get('Origin') != f'{raw.scheme}://{raw.get_host()}':
        raise PermissionDenied('浏览器会话请求来源无效', code='csrf_failed')
    check = CSRFCheck(lambda request: None)
    check.process_request(raw)
    if check.process_view(raw, None, (), {}):
        raise PermissionDenied('浏览器会话请求校验失败', code='csrf_failed')


def clear_refresh_cookie(response):
    response.delete_cookie(refresh_cookie_name(), path=COOKIE_PATH, samesite='Lax')


class BrowserSessionMixin:
    """仅显式请求 cookie 传输时生效；安全检查先于任何凭据签发。"""
    cookie_only = False
    rotate_browser_csrf = True

    def browser_transport(self, request):
        return self.cookie_only or request.headers.get('X-AdminCore-Session') == 'cookie'

    def initial(self, request, *args, **kwargs):
        if self.browser_transport(request):
            require_browser_transport(request)
        return super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if not self.browser_transport(request) or not 200 <= response.status_code < 300:
            return response
        data = getattr(response, 'data', None)
        payload = data.get('data') if isinstance(data, dict) and 'data' in data else data
        if isinstance(payload, dict) and payload.get('access') and payload.get('refresh'):
            refresh = payload.pop('refresh')
            # 已由本次签发/轮换产生，不再次校验时钟，避免到期秒边界变成 500。
            lifetime = max(0, int(UntypedToken(refresh, verify=False)['exp']) - int(timezone.now().timestamp()))
            response.set_cookie(refresh_cookie_name(), refresh, path=COOKIE_PATH, max_age=lifetime,
                                secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite='Lax')
            if self.rotate_browser_csrf:
                rotate_token(request._request)
            payload['session_transport'] = 'cookie'
            payload['csrf_token'] = get_token(request._request)
        response['Cache-Control'] = 'private, no-store'
        return response
