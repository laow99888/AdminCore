from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.schema import envelope, TokenPairSerializer, BROWSER_SESSION_PARAMETERS
from . import totp
from .browser_session import BrowserSessionMixin
from .serializers import UserSerializer
from .recovery_views import StrictSerializer, NoStoreView


class TOTPPasswordRequest(StrictSerializer):
    current_password = serializers.CharField(max_length=1024, trim_whitespace=False, write_only=True)


class TOTPProofRequest(TOTPPasswordRequest):
    otp_code = serializers.RegexField(r'^(?:[0-9]{6}|[0-9a-f]{32})$', max_length=32, trim_whitespace=False, write_only=True)


class TOTPStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    available = serializers.BooleanField()
    recovery_codes_remaining = serializers.IntegerField()


class TOTPSetupSerializer(serializers.Serializer):
    secret = serializers.CharField()
    otpauth_uri = serializers.CharField()
    expires_at = serializers.DateTimeField()


class TOTPResultSerializer(TokenPairSerializer):
    user = UserSerializer()
    recovery_codes = serializers.ListField(child=serializers.CharField(), required=False)


class TOTPView(BrowserSessionMixin, NoStoreView):
    permission_classes = [IsAuthenticated]

    def input(self, request, serializer_class):
        if len(request.body) > 4096:
            raise ValidationError('请求大小超过限制')
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @extend_schema(responses=envelope('TOTPStatusResponse', TOTPStatusSerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': totp.status(request.user)})


class TOTPSetupView(TOTPView):
    @extend_schema(request=TOTPPasswordRequest, responses=envelope('TOTPSetupResponse', TOTPSetupSerializer()))
    def post(self, request):
        self.input(request, TOTPPasswordRequest)
        return Response({'code': 200, 'message': '请录入认证器并确认动态码', 'data': totp.setup(request)})


class TOTPChangeView(TOTPView):
    operation = 'enable'

    @extend_schema(request=TOTPProofRequest, responses=envelope('TOTPChangeResponse', TOTPResultSerializer()),
                   parameters=BROWSER_SESSION_PARAMETERS)
    def post(self, request):
        data = self.input(request, TOTPProofRequest)
        return Response({'code': 200, 'message': '双因素设置已更新', 'data': totp.change(request, self.operation, data['otp_code'])})


class TOTPDisableView(TOTPChangeView):
    operation = 'disable'


class TOTPRecoveryCodesView(TOTPChangeView):
    operation = 'recovery-codes'
