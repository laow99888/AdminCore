"""角色字段级访问策略。

策略只允许引用源码登记的字段，避免把任意模型字段、关系字段或敏感列
通过配置暴露出去。未声明策略的旧角色保持完整字段访问，便于平滑升级。
"""

from collections.abc import Mapping

from rest_framework.exceptions import PermissionDenied, ValidationError


FIELD_POLICY_FIELDS = {
    'user': frozenset({'id', 'username', 'email', 'first_name', 'last_name', 'avatar', 'phone',
                       'is_active', 'login_count', 'created_at', 'profile', 'roles', 'version'}),
    'users': frozenset({'username', 'email', 'first_name', 'last_name', 'phone'}),
    'role': frozenset({'id', 'name', 'description', 'is_active', 'permissions', 'created_at', 'version'}),
    'roles': frozenset({'id', 'name', 'description', 'is_active', 'created_at'}),
    'post': frozenset({'id', 'code', 'name', 'description', 'order', 'is_active', 'version', 'created_at'}),
    'posts': frozenset({'code', 'name', 'description'}),
    'files': frozenset({'id', 'original_name', 'file_type', 'size', 'content_type', 'uploader__username', 'download_count', 'created_at'}),
    'logs': frozenset({'id', 'created_at', 'user__username', 'action', 'resource', 'resource_id', 'status', 'ip_address',
                       'username', 'level', 'request_method'}),
}

RESOURCE_ALIASES = {'users': 'user', 'roles': 'role', 'posts': 'post'}


def canonical_resource(resource):
    return RESOURCE_ALIASES.get(resource, resource)


def validate_field_permissions(value):
    """验证角色字段策略并返回去重后的规范化副本。"""
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError({'field_permissions': '字段策略必须是对象'})
    result = {}
    for raw_resource, raw_policy in value.items():
        resource = canonical_resource(raw_resource)
        allowed = FIELD_POLICY_FIELDS.get(resource)
        if allowed is None or raw_resource != resource:
            raise ValidationError({'field_permissions': f'不支持字段策略资源：{raw_resource}'})
        if not isinstance(raw_policy, Mapping) or set(raw_policy) - {'read', 'write'}:
            raise ValidationError({'field_permissions': f'{resource} 只允许 read/write 两类字段'})
        normalized = {}
        for action in ('read', 'write'):
            fields = raw_policy.get(action, [])
            if not isinstance(fields, list) or any(not isinstance(field, str) for field in fields):
                raise ValidationError({'field_permissions': f'{resource}.{action} 必须是字符串数组'})
            if len(fields) != len(set(fields)):
                raise ValidationError({'field_permissions': f'{resource}.{action} 不能重复'})
            unknown = set(fields) - allowed
            if unknown:
                raise ValidationError({'field_permissions': f'{resource}.{action} 含未知字段：{sorted(unknown)}'})
            normalized[action] = fields
        result[resource] = normalized
    return result


def _declared_policies(user, resource):
    if not user or user.is_superuser or user.is_staff:
        return []
    from .models import Role
    return list(Role.objects.filter(userrole__user=user, is_active=True).values_list('field_permissions', flat=True))


def allowed_fields(user, resource, action):
    """返回当前用户对资源的字段集合；无声明策略时返回完整登记集合。"""
    canonical = canonical_resource(resource)
    all_fields = FIELD_POLICY_FIELDS.get(canonical)
    if all_fields is None:
        raise ValueError(f'未登记字段策略资源：{resource}')
    if user and (user.is_superuser or user.is_staff):
        return set(all_fields)
    policies = [policy.get(canonical) for policy in _declared_policies(user, canonical)
                if isinstance(policy, Mapping) and canonical in policy]
    if not policies:
        return set(all_fields)
    return {field for policy in policies for field in policy.get(action, [])}


def enforce_write_fields(user, resource, fields, *, allow=()):
    allowed = allowed_fields(user, resource, 'write')
    blocked = set(fields) - set(allow) - allowed
    if blocked:
        raise PermissionDenied(f'没有写入字段权限：{", ".join(sorted(blocked))}')


def filter_read_fields(user, resource, data):
    allowed = allowed_fields(user, resource, 'read')
    return {key: value for key, value in data.items() if key in allowed}
