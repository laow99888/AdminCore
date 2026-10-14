"""
认证视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from apps.core.schema import envelope, MessageResponse
from apps.core.schema import TokenPairSerializer, LoginRequestSerializer

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError
from .throttling import LoginRateThrottle
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from rest_framework_simplejwt.utils import get_md5_hash_password
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiTypes
from .profile import (ProfileReadSerializer, ProfileWriteSerializer, AvatarUploadSerializer,
                      ProfileVersionSerializer, update_profile, replace_avatar, remove_avatar, require_avatar_module)
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserSerializer,
    UserRegistrationSerializer,
    ChangePasswordSerializer,
    RefreshTokenSerializer,
)

User = get_user_model()


@extend_schema_view(
    post=extend_schema(request=LoginRequestSerializer, responses=inline_serializer('LoginResponse', fields={'access': serializers.CharField(), 'refresh': serializers.CharField(), 'user': inline_serializer('LoginUser', fields={**{name: serializers.CharField() for name in ['id', 'username', 'email', 'avatar']}, 'must_change_password': serializers.BooleanField()})})),
)
class CustomTokenObtainPairView(TokenObtainPairView):
    """自定义登录视图"""
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except (serializers.ValidationError, AuthenticationFailed):
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

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    @extend_schema(methods=['GET'], responses=envelope('PersonalProfileResponse', ProfileReadSerializer()))
    @extend_schema(methods=['PATCH'], request=ProfileWriteSerializer,
                   responses=envelope('PersonalProfileUpdatedResponse', ProfileReadSerializer()))
    @action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated])
    def profile(self, request):
        user = request.user
        if request.method == 'PATCH':
            serializer = ProfileWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = update_profile(request, serializer.validated_data)
        return Response({'code': 200, 'message': 'success', 'data': ProfileReadSerializer(user).data})

    @extend_schema(methods=['GET'], responses={(200, 'image/png'): OpenApiTypes.BINARY})
    @extend_schema(methods=['POST'], request={'multipart/form-data': AvatarUploadSerializer},
                   responses=envelope('AvatarUpdatedResponse', ProfileReadSerializer()))
    @extend_schema(methods=['DELETE'], request=ProfileVersionSerializer,
                   responses=envelope('AvatarRemovedResponse', ProfileReadSerializer()))
    @action(detail=False, methods=['get', 'post', 'delete'], permission_classes=[IsAuthenticated])
    def avatar(self, request):
        require_avatar_module()
        if request.method == 'GET':
            from apps.core.exceptions import APIError
            from apps.files.models import FileModel
            from apps.files.preview import preview_content
            asset = FileModel.objects.filter(pk=request.user.avatar_file_id, uploader=request.user,
                                             purpose='avatar', is_deleted=False).first()
            if asset is None:
                raise APIError('尚未设置头像', status_code=404)
            content, mime = preview_content(asset)
            response = HttpResponse(content, content_type=mime)
            response['Cache-Control'] = 'private, no-store'
            response['X-Content-Type-Options'] = 'nosniff'
            response['Content-Disposition'] = 'inline; filename="avatar.png"'
            response['Content-Security-Policy'] = "sandbox; default-src 'none'; frame-ancestors 'none'"
            return response
        serializer = (AvatarUploadSerializer if request.method == 'POST' else ProfileVersionSerializer)(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = (replace_avatar if request.method == 'POST' else remove_avatar)(request, serializer.validated_data)
        return Response({'code': 200, 'message': 'success', 'data': ProfileReadSerializer(user).data})

    @action(detail=False, methods=['post'])
    def register(self, request):
        """用户注册"""
        if not settings.ALLOW_PUBLIC_REGISTRATION:
            return Response({'code': 403, 'message': '当前环境未开放注册', 'data': None}, status=403)
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            from .sessions import issue_session
            with transaction.atomic():
                user = serializer.save()
                refresh = issue_session(user, request)
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
        serializer = RefreshTokenSerializer(data=request.data, context={'request': request})
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
        from .sessions import logout_session
        logout_session(request)
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
    @transaction.atomic
    def change_password(self, request):
        """修改密码"""
        user = User.objects.select_for_update().filter(pk=request.user.pk).first()
        if user is None:
            raise AuthenticationFailed('登录凭据已撤销，请重新登录')
        from .sessions import locked_request_session
        locked_request_session(request, user)
        # 锁内再验凭据，防止等待期间管理员重置密码或撤销会话。
        if (request.auth.get('session_version') != user.session_version
                or request.auth.get('hash_password') != get_md5_hash_password(user.password)):
            return Response({'code': 401, 'message': '登录凭据已撤销', 'data': None}, status=401)
        serializer = ChangePasswordSerializer(data=request.data, context={'user': user})
        if serializer.is_valid():
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({
                    'code': 400,
                    'message': '旧密码不正确',
                    'data': None,
                }, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(serializer.validated_data['new_password'])
            user.must_change_password = False
            user.session_version += 1
            user.save(update_fields=['password', 'must_change_password', 'session_version', 'updated_at'])
            from apps.logs.models import OperationLog
            OperationLog.objects.create(user=user, action='update', resource='user', resource_id=str(user.pk),
                                       description='用户完成密码修改', ip_address=request.META.get('REMOTE_ADDR', ''))
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
