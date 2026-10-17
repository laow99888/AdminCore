"""多租户上下文、生命周期和授权辅助函数。"""
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from django.conf import settings
from rest_framework.exceptions import PermissionDenied, ValidationError

_current_tenant = ContextVar('admincore_current_tenant', default=None)

def enabled():
    return bool(getattr(settings, 'ADMINCORE_MULTI_TENANT_ENABLED', False))

def current_tenant_id():
    return _current_tenant.get()


class TenantQuerysetMixin:
    # 每次请求重新限定类级查询集；模型 Manager 不会在 .all() 克隆时重跑。
    # 不使用类 docstring，避免作为 DRF 视图说明继承到所有 OpenAPI 操作。

    def get_queryset(self):
        queryset = super().get_queryset()
        identifier = current_tenant_id() if enabled() else None
        if identifier is not None:
            from .models import BaseModel
            if issubclass(queryset.model, BaseModel):
                queryset = queryset.filter(tenant_id=identifier)
        return queryset

def set_current_tenant(identifier):
    return _current_tenant.set(str(identifier) if identifier is not None else None)

def clear_current_tenant():
    _current_tenant.set(None)

@contextmanager
def tenant_context(identifier):
    token = set_current_tenant(identifier)
    try:
        yield identifier
    finally:
        _current_tenant.reset(token)

def _parse_identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('租户标识必须是 UUID') from None

def activate_for_user(request, user):
    if not enabled() or not getattr(user, 'is_authenticated', False):
        return None
    from .models import Tenant, TenantMembership
    # 只允许这两个身份引导入口在没有租户上下文时工作；业务入口仍强制选租户。
    bootstrap = getattr(request, 'method', '') in {'GET', 'HEAD', 'OPTIONS'} and getattr(request, 'path', '') in {
        '/api/v1/auth/me/', '/api/v1/organization/my-tenants/'}
    header = request.headers.get('X-AdminCore-Tenant', '').strip()
    if bootstrap and not header:
        clear_current_tenant()
        request.tenant = None
        return None
    if header:
        identifier = _parse_identifier(header)
        tenant = Tenant.objects.filter(pk=identifier, status=Tenant.STATUS_ACTIVE).first()
        if tenant is None:
            raise PermissionDenied('租户不存在或已停用')
        if not (user.is_staff or user.is_superuser) and not TenantMembership.objects.filter(
                tenant_id=tenant.pk, user_id=user.pk, is_active=True).exists():
            raise PermissionDenied('当前用户不是该租户成员')
        set_current_tenant(tenant.pk)
        request.tenant = tenant
        return tenant
    if user.is_staff or user.is_superuser:
        request.tenant = None
        return None
    memberships = list(TenantMembership.objects.filter(
        user_id=user.pk, is_active=True, tenant__status=Tenant.STATUS_ACTIVE,
    ).select_related('tenant').order_by('tenant_id'))
    if not memberships:
        raise PermissionDenied('当前用户没有可用租户')
    if len(memberships) > 1:
        raise ValidationError({'tenant': '当前用户属于多个租户，请通过 X-AdminCore-Tenant 指定租户'})
    set_current_tenant(memberships[0].tenant_id)
    request.tenant = memberships[0].tenant
    return memberships[0].tenant

def tenant_membership(user, tenant_id=None):
    from .models import TenantMembership
    query = TenantMembership.objects.filter(user=user, is_active=True)
    if tenant_id is not None:
        query = query.filter(tenant_id=tenant_id)
    return query.select_related('tenant').first()

def can_manage_tenant(user, tenant_id):
    if user.is_staff or user.is_superuser:
        return True
    membership = tenant_membership(user, tenant_id)
    return bool(membership and membership.role in {'owner', 'admin'})
