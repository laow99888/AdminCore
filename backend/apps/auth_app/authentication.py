"""JWT 撤销：退出撤销全部会话，改密使已有凭据立即失效。"""
from django.contrib.auth import get_user_model
from django.db.models import F
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class SessionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if validated_token.get('session_version') != user.session_version:
            raise AuthenticationFailed('登录凭据已撤销', code='session_revoked')
        return user


def revoke_user_sessions(user):
    get_user_model().objects.filter(pk=user.pk).update(session_version=F('session_version') + 1)
