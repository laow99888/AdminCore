"""Only dedicated read-only gateway views opt into this authenticator."""
import hashlib
import hmac
import re
import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound, PermissionDenied, Throttled

from apps.auth_app.sessions import request_ip
from apps.core.modules import module_enabled
from apps.core.query_budget import query_budget
from apps.logs.models import OperationLog
from apps.permissions.permissions import has_permission_code
from .models import APICredential, CredentialUsageDay, ServiceIdentity
from .policy import REQUESTS_PER_MINUTE, available_scopes


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class CredentialRateLimitUnavailable(APIException):
    status_code = 503
    default_detail = '开放凭证限流暂不可用'


def guard_attempt(request):
    """Bound random-secret guessing before querying the database; never cache secrets."""
    now = time.time()
    key = f'api-credential-attempt:{digest(request_ip(request) or "unknown")}:{int(now // 60)}'
    try:
        if cache.add(key, 1, timeout=120):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:
                if cache.add(key, 1, timeout=120):
                    count = 1
                else:
                    count = cache.incr(key)
    except Exception:
        raise CredentialRateLimitUnavailable() from None
    if count > 180:
        raise Throttled(wait=60 - now % 60)


class APICredentialAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'ApiToken'

    def authenticate(self, request):
        if not module_enabled('api_credentials'):
            raise NotFound()
        guard_attempt(request)
        header = get_authorization_header(request)
        match = re.fullmatch(rb'ApiToken ac_([0-9a-f]{32})\.([A-Za-z0-9_-]{43})', header)
        if match is None:
            raise AuthenticationFailed('开放凭证无效或已撤销')
        identifier, secret = match[1].decode(), match[2].decode()
        owner_id = APICredential.objects.filter(pk=identifier).values_list('owner_id', flat=True).first()
        if owner_id is None:
            # Still compare a digest on misses; do not disclose credential existence.
            hmac.compare_digest(digest(secret), '0' * 64)
            raise AuthenticationFailed('开放凭证无效或已撤销')
        with query_budget(), transaction.atomic():
            # Same lock order as creation/revocation and account security operations.
            actor = get_user_model().objects.select_for_update().filter(pk=owner_id).first()
            identity = None
            if actor is not None and actor.is_service_account:
                from apps.core.tenancy import enabled, clear_current_tenant
                from apps.core.models import Tenant
                identity = ServiceIdentity.objects.filter(user=actor).first()
                if (identity is None or actor.is_staff or actor.is_superuser or actor.has_usable_password()
                        or (enabled() and identity.tenant_id is None) or (not enabled() and identity.tenant_id is not None)):
                    raise AuthenticationFailed('开放凭证无效或已撤销')
                if identity.tenant_id is not None:
                    tenant = Tenant.objects.select_for_update().filter(pk=identity.tenant_id, status=Tenant.STATUS_ACTIVE).first()
                    if tenant is None:
                        raise AuthenticationFailed('开放凭证所属租户已失效')
                    header = request.headers.get('X-AdminCore-Tenant', '').strip()
                    if header and header.lower() != str(identity.tenant_id):
                        raise PermissionDenied('机器身份不能切换所属租户')
                    # 固定创建时租户，同时复核成员资格；不能凭额外成员关系切换租户。
                    from apps.core.tenancy import set_current_tenant
                    from apps.core.models import TenantMembership
                    if not TenantMembership.objects.filter(user=actor, tenant_id=identity.tenant_id, is_active=True).exists():
                        raise AuthenticationFailed('开放凭证所属租户成员资格已失效')
                    set_current_tenant(identity.tenant_id)
                    request.tenant = tenant
                else:
                    clear_current_tenant()
                    request.tenant = None
            credential = APICredential.objects.select_for_update().filter(pk=identifier).first()
            now = timezone.now()
            if (actor is None or credential is None or not actor.is_active or actor.must_change_password
                    or credential.revoked_at is not None or credential.expires_at <= now
                    or credential.session_version != actor.session_version
                    or (identity is None and not hmac.compare_digest(credential.password_digest, digest(actor.password)))
                    or (identity is not None and credential.password_digest != '')
                    or not hmac.compare_digest(credential.secret_digest, digest(secret))):
                raise AuthenticationFailed('开放凭证无效或已撤销')
            callback = getattr(request, 'resolver_match', None)
            view = getattr(request, 'parser_context', {}).get('view')
            scope = getattr(view, 'credential_scope', None)
            if scope is None:
                scope = getattr(getattr(getattr(callback, 'func', None), 'cls', None), 'credential_scope', None)
            if (request.method not in {'GET', 'HEAD', 'OPTIONS'} or scope not in available_scopes()
                    or scope not in credential.scopes or not has_permission_code(actor, scope)):
                raise PermissionDenied('开放凭证无此只读能力')
            if identity is not None:
                from apps.permissions.models import UserRole, RolePermission
                roles = list(UserRole.all_objects.filter(user=actor).select_related('role'))
                codes = set(RolePermission.all_objects.filter(role_id__in=[row.role_id for row in roles])
                            .values_list('permission__code', flat=True))
                if (not roles or any(not row.role.is_active or row.role.tenant_id != identity.tenant_id
                                     or row.tenant_id != identity.tenant_id for row in roles)
                        or not codes or not codes <= set(available_scopes())):
                    raise PermissionDenied('机器身份专用只读角色已失效')
            from apps.core.tenancy import activate_for_user
            if identity is None:
                activate_for_user(request, actor)
            window = int(now.timestamp() // 60)
            if credential.usage_window == window and credential.usage_count >= REQUESTS_PER_MINUTE:
                raise Throttled(wait=60 - now.timestamp() % 60)
            first = credential.last_used_at is None
            new_window = credential.usage_window != window
            credential.usage_count = 1 if new_window else credential.usage_count + 1
            credential.usage_window = window
            credential.accepted_requests += 1
            fields = ['usage_count', 'usage_window', 'accepted_requests']
            if first or new_window:
                credential.last_used_at = now
                fields.append('last_used_at')
            credential.save(update_fields=fields)
            # 同一凭证行锁串行化计数；仅保留最近90个UTC自然日。
            usage, _ = CredentialUsageDay.objects.get_or_create(credential=credential, day=now.date())
            usage.requests += 1
            usage.save(update_fields=['requests'])
            CredentialUsageDay.objects.filter(credential=credential, day__lt=now.date() - timedelta(days=89)).delete()
            # One activation event per credential, not one growing SQL audit row per request.
            if first:
                OperationLog.objects.create(user=actor, actor_identifier=str(actor.pk), action='read',
                    resource='api_credential', resource_id=str(credential.pk), description='开放凭证首次使用',
                    request_id=getattr(request, 'request_id', ''), ip_address=request_ip(request) or '127.0.0.1')
        return actor, credential
