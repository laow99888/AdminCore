"""
认证序列化器
"""

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.utils import get_md5_hash_password
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """自定义 JWT Token 序列化器"""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # 添加自定义声明
        token['user_id'] = str(user.id)
        token['username'] = user.username
        token['email'] = user.email
        token['session_version'] = user.session_version
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # 登录成功：记录登录日志并累计登录次数
        from django.db.models import F
        from apps.logs.models import LoginLog

        request = self.context.get('request')
        ip = request.META.get('REMOTE_ADDR', '') if request else ''
        user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''
        LoginLog.objects.create(
            user=self.user, username=self.user.username, status='success',
            ip_address=ip, user_agent=user_agent,
        )
        User.objects.filter(pk=self.user.pk).update(
            login_count=F('login_count') + 1, last_login_ip=ip,
        )
        # 添加用户信息
        data['user'] = {
            'id': str(self.user.id),
            'username': self.user.username,
            'email': self.user.email,
            'avatar': self.user.avatar,
            'must_change_password': self.user.must_change_password,
        }
        return data


class UserSerializer(serializers.ModelSerializer):
    """用户序列化器"""
    permissions = serializers.SerializerMethodField()
    has_avatar = serializers.SerializerMethodField()
    avatar_enabled = serializers.SerializerMethodField()

    def get_has_avatar(self, user) -> bool:
        return bool(user.avatar_file_id)

    def get_avatar_enabled(self, user) -> bool:
        from apps.core.modules import module_enabled
        return module_enabled('files')

    def get_permissions(self, user) -> list[str]:
        if user.must_change_password:
            return []
        from apps.permissions.permissions import permission_codes
        return permission_codes(user)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'avatar', 'phone', 'is_active', 'is_staff', 'is_superuser', 'permissions', 'must_change_password', 'profile_version', 'has_avatar', 'avatar_enabled', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class UserRegistrationSerializer(serializers.ModelSerializer):
    """用户注册序列化器"""
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': '两次输入的密码不一致'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """修改密码序列化器"""
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password2 = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password': '两次输入的密码不一致'})
        if attrs['new_password'] == attrs['old_password']:
            raise serializers.ValidationError({'new_password': '新密码不能与当前密码相同'})
        try:
            validate_password(attrs['new_password'], self.context.get('user'))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.messages}) from exc
        return attrs


class RefreshTokenSerializer(TokenRefreshSerializer):
    """刷新 Token 序列化器"""
    def validate(self, attrs):
        token = RefreshToken(attrs['refresh'])
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=token.get('user_id')).first()
            if (user is None or not user.is_active
                    or token.get('session_version') != user.session_version
                    or token.get('hash_password') != get_md5_hash_password(user.password)):
                raise TokenError('登录凭据已撤销')
            # 锁内重新验证黑名单，避免并发刷新重复使用同一凭据。
            return super().validate(attrs)
