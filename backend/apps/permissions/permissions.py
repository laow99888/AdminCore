"""
自定义权限类
"""

from rest_framework.permissions import BasePermission
from .models import RolePermission


def permission_codes(user):
    if user.is_superuser or user.is_staff:
        return ['*']
    return list(RolePermission.objects.filter(
        role__is_active=True, role__userrole__user=user,
    ).values_list('permission__code', flat=True).distinct())


def has_permission_code(user, code):
    return bool(user and user.is_authenticated and user.is_active
                and ('*' in (codes := permission_codes(user)) or code in codes))


class HasPermission(BasePermission):
    """检查用户是否有特定权限"""

    def has_permission(self, request, view):
        """检查用户是否有访问权限"""
        if not request.user or not request.user.is_authenticated:
            return False

        required = getattr(view, 'required_permission', None)
        action_map = getattr(view, 'permission_map', {})
        required = action_map.get(getattr(view, 'action', ''), required)
        if required is None:
            required = action_map.get(request.method.lower())
        return bool(required and has_permission_code(request.user, required))

    def has_object_permission(self, request, view, obj):
        """检查对象级别的权限"""
        if request.user and request.user.is_superuser:
            return True
        return True


class IsAdmin(BasePermission):
    """仅管理员可以访问"""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))


class IsOwnerOrAdmin(BasePermission):
    """仅所有者或管理员可以访问"""

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.user == request.user
