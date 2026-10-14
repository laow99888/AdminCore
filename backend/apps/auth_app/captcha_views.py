from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.schema import envelope
from .login_captcha import issue_challenge
from .recovery_views import NoStoreView, StrictSerializer


class LoginCaptchaRequest(StrictSerializer):
    username = serializers.CharField(max_length=150)


class LoginCaptchaResponse(serializers.Serializer):
    required = serializers.BooleanField()
    challenge_id = serializers.UUIDField(required=False)
    image = serializers.CharField(required=False)
    expires_in = serializers.IntegerField(required=False)


class LoginCaptchaView(NoStoreView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=LoginCaptchaRequest, responses=envelope('LoginCaptchaEnvelope', LoginCaptchaResponse()))
    def post(self, request):
        if len(request.body) > 1024:
            raise ValidationError('请求大小超过限制')
        serializer = LoginCaptchaRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({'code': 200, 'message': 'success', 'data': issue_challenge(request, serializer.validated_data['username'])})
