"""Linked identity guards for both signed JWTs and stored background session IDs."""
from django.db.models import F, Q
from rest_framework.exceptions import AuthenticationFailed

from apps.core.modules import module_enabled
from .configuration import SSOUnavailable, provider
from .models import SSOSession


def valid_links(config):
    return SSOSession.objects.filter(identity__revoked_at__isnull=True,
        identity__issuer=config.issuer, identity__user_id=F('session__user_id'),
        binding_version=F('identity__binding_version'), config_digest=config.fingerprint)


def filter_active_linked_sessions(queryset):
    """Keep local sessions and currently valid SSO links in one lockable SQL query.

    The outer AuthSession query must not acquire a nullable SSO LEFT JOIN:
    PostgreSQL cannot apply FOR UPDATE to its nullable side. Subqueries keep
    actor -> session locking usable by workers without trusting a JWT marker.
    """
    links = SSOSession.objects.all()
    valid = links.none()
    if module_enabled('sso'):
        try:
            valid = valid_links(provider())
        except SSOUnavailable:
            pass  # Missing/rotated provider configuration invalidates only SSO sessions.
    return queryset.filter(~Q(pk__in=links.values('session_id'))
                           | Q(pk__in=valid.values('session_id')))


def validate_linked_session(session, user, token):
    if token.get('sso') is not True:
        return
    try:
        valid = (module_enabled('sso') and valid_links(provider()).filter(
            session_id=session.pk, identity__user_id=user.pk).exists())
    except SSOUnavailable:
        valid = False
    if not valid:
        raise AuthenticationFailed('企业登录会话已撤销，请重新登录', code='session_revoked')
