"""邮箱安全接口：匿名入口统一回复，所有响应禁止缓存。"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.schema import envelope, MessageResponse
from . import recovery
from .profile import ProfileReadSerializer


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError({'non_field_errors': ['请求包含不允许的字段']})
        return super().to_internal_value(data)


class RecoveryConfigSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class RecoveryRequestSerializer(StrictSerializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)


class CodeSerializer(StrictSerializer):
    code = serializers.CharField(max_length=97, min_length=97, trim_whitespace=False, write_only=True)

    def validate_code(self, value):
        recovery.code_identifier(value)
        return value


class RecoveryResetSerializer(CodeSerializer):
    new_password = serializers.CharField(max_length=1024, trim_whitespace=False, write_only=True)
    new_password2 = serializers.CharField(max_length=1024, trim_whitespace=False, write_only=True)


class VerificationRequestSerializer(StrictSerializer):
    current_password = serializers.CharField(max_length=1024, trim_whitespace=False, write_only=True)


class NoStoreView(APIView):
    parser_classes = [JSONParser]
    throttle_classes = []

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def input(self, request, serializer_class):
        recovery.require_email_service()
        content_length = request.META.get('CONTENT_LENGTH', '0')
        try:
            too_large = int(content_length or 0) > 4096
        except (ValueError, TypeError):
            too_large = True
        if too_large or len(request.body) > 4096:
            raise ValidationError('请求大小超过限制')
        serializer = serializer_class(data=request.data)
        # 所有凭据格式失败也保持统一，不回显输入。
        if not serializer.is_valid():
            errors = dict(serializer.errors)
            if 'code' in errors:
                errors['code'] = [recovery.INVALID_CODE]
            raise ValidationError(errors)
        return serializer.validated_data


class RecoveryConfigView(NoStoreView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=envelope('RecoveryConfigResponse', RecoveryConfigSerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': {'enabled': recovery.recovery_enabled()}})


class RecoveryRequestView(NoStoreView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=RecoveryRequestSerializer, responses={202: MessageResponse})
    def post(self, request):
        data = self.input(request, RecoveryRequestSerializer)
        recovery.limited_request(request, 'reset-request', data['username'].casefold())
        recovery.request_reset(request, **data)
        return Response({'code': 202, 'message': recovery.REQUEST_MESSAGE, 'data': None}, status=202)


class RecoveryResetView(NoStoreView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=RecoveryResetSerializer, responses=MessageResponse)
    def post(self, request):
        # 在解析/验证凭据前按 IP 限流，格式错误也不能无限尝试。
        recovery.require_email_service()
        recovery.limited_request(request, 'reset-code')
        data = self.input(request, RecoveryResetSerializer)
        recovery.limited_request(request, 'reset-identity', data['code'][:32])
        recovery.reset_password(request, **data)
        return Response({'code': 200, 'message': '密码已重置，请重新登录', 'data': None})


class VerificationRequestView(NoStoreView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=VerificationRequestSerializer, responses={202: MessageResponse})
    def post(self, request):
        self.input(request, VerificationRequestSerializer)
        recovery.limited_request(request, 'verify-request', str(request.user.pk))
        recovery.request_verification(request)
        return Response({'code': 202, 'message': '验证邮件已登记，请稍后查收', 'data': None}, status=202)


class VerificationConfirmView(NoStoreView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CodeSerializer, responses=envelope('EmailVerificationProfileResponse', ProfileReadSerializer()))
    def post(self, request):
        recovery.require_email_service()
        recovery.limited_request(request, 'verify-code', str(request.user.pk))
        data = self.input(request, CodeSerializer)
        user = recovery.confirm_verification(request, data['code'])
        return Response({'code': 200, 'message': '邮箱验证成功', 'data': ProfileReadSerializer(user).data})
