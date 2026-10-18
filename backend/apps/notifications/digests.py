"""显式 V2 业务提醒及摘要。偏好不授予权限，摘要不冻结业务字段。"""
import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.codegen.integrations import registered_module
from apps.core.modules import module_enabled
from apps.core.tenancy import current_tenant_id, enabled, tenant_context
from apps.permissions.permissions import has_permission_code
from .models import BusinessNotice, Notification
from .preferences import preference_for, subscribed

MAX_REFRESH = 500


def locked_users():
    options = {'no_key': True} if connection.features.has_select_for_no_key_update else {}
    return get_user_model().objects.select_for_update(**options)


def tenant_id():
    return current_tenant_id() if enabled() else None


def recipient_available(user, scope):
    if not user or not user.is_active or user.must_change_password:
        return False
    if scope is None:
        return not enabled() or bool(user.is_staff or user.is_superuser)
    from apps.core.models import Tenant, TenantMembership
    return (Tenant.objects.filter(pk=scope, status=Tenant.STATUS_ACTIVE).exists()
            and TenantMembership.objects.filter(tenant_id=scope, user=user, is_active=True).exists())


def reference_for(user, resource, object_id, scope):
    """仅显式生成模块；路径来自受信菜单，记录范围来自原服务 visible。"""
    if (not module_enabled('notifications') or not recipient_available(user, scope)
            or not module_enabled(resource) or not has_permission_code(user, resource + ':read')):
        return None
    from apps.core.modules import MODULES
    declaration = next((item for item in MODULES if item.key == resource), None)
    if declaration is None:
        return None
    menu = next((item for item in declaration.menus if item.permission == resource + ':read'
                 and item.path in declaration.paths and item.path.startswith('/') and not item.path.startswith('//')), None)
    if menu is None:
        return None
    try:
        schema, _, service = registered_module(resource)
    except NotFound:
        return None
    with tenant_context(scope):
        # 不依赖 manager 在空租户时的宽范围兼容行为；平台也不能跨租户摘要。
        if not service.visible(user).filter(tenant_id=scope, pk=object_id).exists():
            return None
    return {'resource': resource, 'label': schema['title'], 'object_id': str(object_id), 'path': menu.path}


@transaction.atomic
def enqueue_business_notice(recipient, resource, object_id, event_key, *, now=None):
    """受信业务代码事务内调用；同租户/用户/事件键永久去重，变化引用拒绝。"""
    if not isinstance(event_key, str) or not 1 <= len(event_key) <= 180:
        raise ValidationError('业务提醒需要稳定且不超过180字符的事件键')
    scope, now = tenant_id(), now or timezone.now()
    # 与偏好写入、刷新相同，先锁用户，后锁通知记录。
    user = locked_users().filter(pk=recipient.pk).first()
    reference = reference_for(user, resource, object_id, scope)
    if reference is None:
        raise NotFound()
    key = hashlib.sha256(f'{scope}:{user.pk}:{event_key}'.encode()).hexdigest()
    existing = BusinessNotice.all_objects.filter(event_key=key).first()
    if existing:
        if existing.resource != resource or str(existing.object_id) != str(object_id):
            from apps.core.system_views import VersionConflict
            raise VersionConflict()
        return existing, False
    preference = preference_for(user.pk, scope)
    accepted = subscribed(preference, 'business.update', 'inapp')
    digest = preference is not None and preference.business_delivery_mode == 'digest'
    row = BusinessNotice.all_objects.create(
        tenant_id=scope, recipient=user, resource=resource, object_id=object_id, event_key=key,
        due_at=now + timedelta(minutes=preference.digest_minutes if digest else 0),
        expires_at=now + timedelta(days=7), state='pending' if accepted else 'suppressed')
    if accepted and not digest:
        _publish([row], user, scope, digest=False)
    return row, True


def _publish(rows, user, scope, *, digest):
    # 不写标题/业务键/字段快照。展开时再次解析引用，原详情 API 仍独立鉴权。
    notice = Notification.all_objects.create(tenant_id=scope, recipient=user,
        title='业务通知摘要' if digest else '业务更新提醒',
        content=f'{len(rows)} 条业务更新，请展开查看当前有权访问的记录。' if digest else '请展开查看当前有权访问的业务记录。',
        notification_type='system', data={'business_digest': True})
    BusinessNotice.all_objects.filter(pk__in=[row.pk for row in rows], state='pending').update(
        state='published', notification=notice, updated_at=timezone.now())
    for row in rows:
        row.state, row.notification = 'published', notice
    return notice


@transaction.atomic
def refresh_recipient(user_id, scope, *, limit=MAX_REFRESH, now=None):
    now = now or timezone.now()
    if type(limit) is not int or not 1 <= limit <= MAX_REFRESH:
        raise ValueError('notification_digest_limit_must_be_1_to_500')
    if not module_enabled('notifications'):
        return {'processed': 0, 'published': 0, 'suppressed': 0, 'summaries': 0}
    user = locked_users().filter(pk=user_id).first()
    rows = list(BusinessNotice.all_objects.select_for_update().filter(
        tenant_id=scope, recipient_id=user_id, state='pending', due_at__lte=now).order_by('due_at', 'pk')[:limit])
    preference = preference_for(user_id, scope)
    allowed = recipient_available(user, scope) and subscribed(preference, 'business.update', 'inapp')
    visible, suppressed = [], []
    for row in rows:
        if allowed and row.expires_at > now and reference_for(user, row.resource, row.object_id, scope):
            visible.append(row)
        else:
            suppressed.append(row.pk)
    if suppressed:
        BusinessNotice.all_objects.filter(pk__in=suppressed, state='pending').update(state='suppressed', updated_at=now)
    if visible:
        _publish(visible, user, scope, digest=True)
    return {'processed': len(rows), 'published': len(visible), 'suppressed': len(suppressed), 'summaries': int(bool(visible))}


def refresh_due(*, limit=MAX_REFRESH, scope=None, all_tenants=False, now=None):
    """后台受信调用；全局领取，但每个用户的事务显式恢复租户与重新授权。"""
    if type(limit) is not int or not 1 <= limit <= MAX_REFRESH:
        raise ValueError('notification_digest_limit_must_be_1_to_500')
    result = {'processed': 0, 'published': 0, 'suppressed': 0, 'summaries': 0}
    if not module_enabled('notifications'):
        return result
    now = now or timezone.now()
    pending = BusinessNotice.all_objects.filter(state='pending', due_at__lte=now)
    if not all_tenants:
        pending = pending.filter(tenant_id=scope)
    # 只取有界候选；并发刷新在用户行锁后复查 pending，不重复生成摘要。
    candidates = list(pending.order_by('due_at', 'pk').values_list('recipient_id', 'tenant_id')[:limit])
    for user_id, recipient_scope in dict.fromkeys(candidates):
        remaining = limit - result['processed']
        if remaining <= 0:
            break
        with tenant_context(recipient_scope):
            counts = refresh_recipient(user_id, recipient_scope, limit=remaining, now=now)
        result = {key: result[key] + counts[key] for key in result}
    return result


def digest_references(user, notification_id):
    scope = tenant_id()
    notification = Notification.all_objects.filter(tenant_id=scope, recipient=user, pk=notification_id,
                                                   data__business_digest=True).first()
    if notification is None or not recipient_available(user, scope):
        raise NotFound()
    rows = BusinessNotice.all_objects.filter(tenant_id=scope, recipient=user, notification=notification, state='published').order_by('pk')
    references, seen = [], set()
    for row in rows[:MAX_REFRESH]:
        key = row.resource, row.object_id
        if key not in seen and (value := reference_for(user, row.resource, row.object_id, scope)):
            references.append(value)
            seen.add(key)
    return {'items': references, 'authorization_checked_at': timezone.now()}
