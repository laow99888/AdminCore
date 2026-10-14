"""JWT 设备会话：当前退出与全局版本撤销分别校验。"""
from django.contrib.auth import get_user_model
from django.db.models import F
from rest_framework_simplejwt.authentication import JWTAuthentication
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
        from .sessions import check_request_session
        check_request_session(validated_token, user)
        return user


def revoke_user_sessions(user):
    get_user_model().objects.filter(pk=user.pk).update(session_version=F('session_version') + 1)
