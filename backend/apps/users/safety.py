"""所有用户管理入口共用的管理员保全规则。"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.core.exceptions import PermissionDenied


def lock_management_users(identifiers=()):
    # 与目标和操作者按同一顺序锁定，串行化并发停用最后管理员的请求。
    return list(get_user_model().objects.select_for_update().filter(
        Q(pk__in=identifiers) | (Q(is_active=True) & (Q(is_staff=True) | Q(is_superuser=True)))
    ).order_by('pk'))


def protect_management_access(actor, targets, *, deleting=False, values=None):
    values = values or {}
    destructive = deleting or values.get('is_active') is False
    if destructive and any(row.pk == actor.pk for row in targets):
        raise PermissionDenied('不能删除或停用当前登录账号')
    removed = [row.pk for row in targets if row.is_active and (row.is_staff or row.is_superuser)
               and (destructive or not (values.get('is_staff', row.is_staff)
                                       or values.get('is_superuser', row.is_superuser)))]
    if removed and not get_user_model().objects.filter(is_active=True).filter(
            Q(is_staff=True) | Q(is_superuser=True)).exclude(pk__in=removed).exists():
        raise PermissionDenied('至少保留一个启用的管理员账号')
