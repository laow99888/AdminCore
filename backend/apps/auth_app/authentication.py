"""JWT 撤销：退出撤销全部会话，改密使已有凭据立即失效。"""
from django.contrib.auth import get_user_model
from django.db.models import F
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied


class SessionJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result and result[0].must_change_password:
            from .views import AuthViewSet
            callback = request.resolver_match.func
            allowed = (getattr(callback, 'cls', None) is AuthViewSet
                       and getattr(callback, 'actions', {}).get(request.method.lower())
                       in {'me', 'logout', 'change_password'})
            if not allowed:
                raise PermissionDenied({'reason': 'password_change_required', 'detail': '请先修改初始密码'})
        return result

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if validated_token.get('session_version') != user.session_version:
            raise AuthenticationFailed('登录凭据已撤销', code='session_revoked')
        return user


def revoke_user_sessions(user):
    get_user_model().objects.filter(pk=user.pk).update(session_version=F('session_version') + 1)
