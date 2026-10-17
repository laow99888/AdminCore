"""Cookie 刷新/退出端点；不使用过期 access，也不把 Cookie 当作业务接口鉴权。"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework_simplejwt.exceptions import TokenError

from apps.core.exceptions import APIError
from apps.core.schema import envelope, TokenPairSerializer, MessageResponse
from .browser_session import BrowserSessionMixin, refresh_cookie_name, clear_refresh_cookie
from .models import AuthSession
from .recovery_views import NoStoreView, StrictSerializer
from .serializers import RefreshTokenSerializer
from .sessions import SessionRefreshToken, session_id, validate_session, audit_session


class BrowserSessionRequest(StrictSerializer):
    session_id = serializers.UUIDField(required=False)


class BrowserLogoutRequest(StrictSerializer):
    session_id = serializers.UUIDField()


class BrowserCSRFSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


CSRF_HEADER = OpenApiParameter('X-CSRFToken', str, OpenApiParameter.HEADER, required=True)


class BrowserAccessSerializer(TokenPairSerializer):
    # 此端点从不返回 refresh，schema 也不发布该字段。
    refresh = None
    session_transport = serializers.ChoiceField(choices=['cookie'])
    csrf_token = serializers.CharField()


def matching_session(token, expected):
    if expected is not None and session_id(token) != expected:
        raise APIError('浏览器会话已变化，请重新加载', code='session_changed', status_code=409)


class BrowserSessionView(BrowserSessionMixin, NoStoreView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = api_settings.DEFAULT_THROTTLE_CLASSES
    cookie_only = True
    rotate_browser_csrf = False

    def values(self, request, serializer_class):
        if len(request.body) > 4096:
            raise ValidationError('请求大小超过限制')
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @extend_schema(responses={200: envelope('BrowserCSRFResponse', BrowserCSRFSerializer()),
                              403: MessageResponse, 404: MessageResponse, 429: MessageResponse})
    def get(self, request):
        return Response({'code': 200, 'message': 'success',
                         'data': {'csrf_token': get_token(request._request)}})

    @extend_schema(request=BrowserSessionRequest,
                   parameters=[CSRF_HEADER],
                   responses={200: envelope('BrowserAccessResponse', BrowserAccessSerializer()),
                              **{code: MessageResponse for code in (400, 401, 403, 404, 409, 429)}})
    def post(self, request):
        values = self.values(request, BrowserSessionRequest)
        try:
            token = SessionRefreshToken(request.COOKIES.get(refresh_cookie_name(), ''))
            matching_session(token, values.get('session_id'))
            tokens = RefreshTokenSerializer(context={'request': request}).rotate(token)
        except TokenError:
            raise AuthenticationFailed('登录凭据已撤销，请重新登录') from None
        # 失败响应不清除 Cookie，防止较旧的并发失败响应覆盖另一次成功轮换。
        return Response({'code': 200, 'message': 'success', 'data': tokens})

    @extend_schema(request=BrowserLogoutRequest, parameters=[CSRF_HEADER],
                   responses={204: None, **{code: MessageResponse for code in (400, 403, 404, 409, 429)}})
    def delete(self, request):
        values = self.values(request, BrowserLogoutRequest)
        try:
            token = SessionRefreshToken(request.COOKIES.get(refresh_cookie_name(), ''))
            matching_session(token, values['session_id'])
            with transaction.atomic():
                actor = get_user_model().objects.select_for_update().filter(pk=token.get('user_id')).first()
                if actor is not None:
                    session = AuthSession.objects.select_for_update().filter(pk=session_id(token), user=actor).first()
                    validate_session(session, actor, token)
                    if session.refresh_jti == token['jti']:
                        session.revoked_at = timezone.now()
                        session.save(update_fields=['revoked_at'])
                        audit_session(request, actor, 'logout', session.pk)
        except (TokenError, AuthenticationFailed):
            # 已过期或已撤销仍允许幂等退出；不会清除其它设备的服务端会话。
            pass
        response = Response(status=204)
        clear_refresh_cookie(response)
        return response

    def get_authenticate_header(self, request):
        return 'Bearer'
