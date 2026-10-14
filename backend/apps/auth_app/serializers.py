"""
认证序列化器
"""

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import TokenError
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """自定义 JWT Token 序列化器"""

    @classmethod
    def get_token(cls, user):
        from .sessions import issue_session
        return issue_session(user)

    @transaction.atomic
    def validate(self, attrs):
        from rest_framework_simplejwt.serializers import TokenObtainSerializer
        from django.db.models import F
        from django.utils import timezone
        from apps.logs.models import LoginLog
        from .sessions import issue_session, request_ip, agent_hint

        TokenObtainSerializer.validate(self, attrs)
        # 认证后重新锁定用户；等待期间的密码/状态/全局撤销变化不得签发会话。
        fresh = User.objects.select_for_update().filter(pk=self.user.pk).first()
        if (fresh is None or not fresh.is_active or fresh.password != self.user.password
                or fresh.session_version != self.user.session_version):
            from rest_framework.exceptions import AuthenticationFailed
            raise AuthenticationFailed('登录凭据已撤销，请重新登录')
        self.user = fresh
        request = self.context.get('request')
        refresh = issue_session(fresh, request)
        ip = request_ip(request) or '0.0.0.0'
        LoginLog.objects.create(user=fresh, username=fresh.username, status='success',
            ip_address=ip, user_agent=agent_hint(request))
        User.objects.filter(pk=fresh.pk).update(login_count=F('login_count') + 1,
            last_login_ip=ip, last_login=timezone.now())
        return {'refresh': str(refresh), 'access': str(refresh.access_token), 'user': {
            'id': str(fresh.pk), 'username': fresh.username, 'email': fresh.email,
            'avatar': fresh.avatar, 'must_change_password': fresh.must_change_password}}


class UserSerializer(serializers.ModelSerializer):
    """用户序列化器"""
    permissions = serializers.SerializerMethodField()
    has_avatar = serializers.SerializerMethodField()
    avatar_enabled = serializers.SerializerMethodField()
    email_verified = serializers.BooleanField(read_only=True)
    recovery_enabled = serializers.SerializerMethodField()

    def get_recovery_enabled(self, user) -> bool:
        from .recovery import recovery_enabled
        return recovery_enabled()

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
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'avatar', 'phone', 'is_active', 'is_staff', 'is_superuser', 'permissions', 'must_change_password', 'profile_version', 'has_avatar', 'avatar_enabled', 'email_verified', 'recovery_enabled', 'created_at', 'updated_at')
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
    """锁定用户及设备会话后，单次轮换 refresh；绝对期限不延长。"""
    def validate(self, attrs):
        from .sessions import SessionRefreshToken
        return self.rotate(SessionRefreshToken(attrs['refresh']))

    @transaction.atomic
    def rotate(self, token):
        from django.utils import timezone
        from .models import AuthSession
        from .sessions import session_id, validate_session, audit_session
        from rest_framework.exceptions import AuthenticationFailed
        try:
            user = User.objects.select_for_update().filter(pk=token.get('user_id')).first()
        except (ValueError, TypeError, DjangoValidationError):
            raise TokenError('登录凭据已撤销')
        if user is None:
            raise TokenError('登录凭据已撤销')
        try:
            session = AuthSession.objects.select_for_update().filter(pk=session_id(token), user=user).first()
            validate_session(session, user, token)
        except AuthenticationFailed as exc:
            raise TokenError('登录凭据已撤销') from exc
        if session.refresh_jti != token['jti']:
            raise TokenError('刷新凭据已使用')
        # 超过普通 access 生命周期仍不得越过设备绝对期限。
        token.check_blacklist()
        token.blacklist()
        token.set_jti()
        token.set_iat()
        token.set_exp()
        token['exp'] = min(token['exp'], int(session.expires_at.timestamp()))
        token.outstand()
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        OutstandingToken.objects.filter(jti=token['jti']).update(token='')
        session.refresh_jti = token['jti']
        session.last_seen_at = timezone.now()
        session.save(update_fields=['refresh_jti', 'last_seen_at'])
        audit_session(self.context.get('request'), user, 'refresh', session.pk)
        return {'access': str(token.access_token), 'refresh': str(token)}
