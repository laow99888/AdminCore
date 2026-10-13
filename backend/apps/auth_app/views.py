"""
认证视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from apps.core.schema import envelope, MessageResponse
from apps.core.schema import TokenPairSerializer, LoginRequestSerializer

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError
from .authentication import revoke_user_sessions
from .throttling import LoginRateThrottle
from django.contrib.auth import get_user_model
from django.conf import settings
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserSerializer,
    UserRegistrationSerializer,
    ChangePasswordSerializer,
    RefreshTokenSerializer,
)

User = get_user_model()


@extend_schema_view(
    post=extend_schema(request=LoginRequestSerializer, responses=inline_serializer('LoginResponse', fields={'access': serializers.CharField(), 'refresh': serializers.CharField(), 'user': inline_serializer('LoginUser', fields={name: serializers.CharField() for name in ['id', 'username', 'email', 'avatar']})})),
)
class CustomTokenObtainPairView(TokenObtainPairView):
    """自定义登录视图"""
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except Exception:
            # 登录失败（用户名不存在/密码错误）也记录登录日志
            from apps.logs.models import LoginLog
            LoginLog.objects.create(
                username=str(request.data.get('username', '')),
                status='failed',
                ip_address=request.META.get('REMOTE_ADDR', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                error_message='用户名或密码错误',
            )
            raise


@extend_schema_view(
    register=extend_schema(request=UserRegistrationSerializer, responses={201: envelope('RegisterResponse', inline_serializer('RegisteredSession', fields={'access': serializers.CharField(), 'refresh': serializers.CharField(), 'user': UserSerializer()}))}),
    refresh=extend_schema(request=inline_serializer('RefreshRequest', fields={'refresh': serializers.CharField()}), responses=envelope('RefreshResponse', TokenPairSerializer())),
    logout=extend_schema(request=None, responses=MessageResponse),
    me=extend_schema(responses=envelope('CurrentUserResponse', UserSerializer())),
    change_password=extend_schema(request=ChangePasswordSerializer, responses=MessageResponse),
)
class AuthViewSet(viewsets.ViewSet):
    """认证相关端点"""
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def register(self, request):
        """用户注册"""
        if not settings.ALLOW_PUBLIC_REGISTRATION:
            return Response({'code': 403, 'message': '当前环境未开放注册', 'data': None}, status=403)
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = CustomTokenObtainPairSerializer.get_token(user)
            return Response({
                'code': 201,
                'message': '注册成功',
                'data': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'user': UserSerializer(user).data,
                }
            }, status=status.HTTP_201_CREATED)
        return Response({
            'code': 400,
            'message': '注册失败',
            'data': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], authentication_classes=[])
    def refresh(self, request):
        """刷新 Token

        注意保持 AllowAny（类默认）：调用时机是 access 已过期，
        请求头里没有有效 Bearer，鉴权只依赖 body 中的 refresh token。
        """
        serializer = RefreshTokenSerializer(data=request.data)
        try:
            if serializer.is_valid():
                return Response({
                    'code': 200,
                    'message': 'success',
                    'data': serializer.validated_data,
                })
        except TokenError:
            return Response({
                    'code': 400,
                    'message': 'Token 无效',
                    'data': None,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'code': 400,
            'message': '刷新失败',
            'data': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """登出"""
        revoke_user_sessions(request.user)
        return Response({
            'code': 200,
            'message': '登出成功',
            'data': None,
        })

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """获取当前用户信息"""
        return Response({
            'code': 200,
            'message': 'success',
            'data': UserSerializer(request.user).data,
        })

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """修改密码"""
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({
                    'code': 400,
                    'message': '旧密码不正确',
                    'data': None,
                }, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({
                'code': 200,
                'message': '密码修改成功',
                'data': None,
            })
        return Response({
            'code': 400,
            'message': '修改失败',
            'data': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)
