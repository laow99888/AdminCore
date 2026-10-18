"""角色字段级访问策略。

策略只允许引用源码登记的字段，避免把任意模型字段、关系字段或敏感列
通过配置暴露出去。未声明策略的旧角色保持完整字段访问，便于平滑升级。
"""

from collections.abc import Mapping

from rest_framework.exceptions import PermissionDenied, ValidationError


FIELD_POLICY_FIELDS = {
    'user': frozenset({'id', 'username', 'email', 'first_name', 'last_name', 'avatar', 'phone',
                       'is_active', 'login_count', 'created_at', 'date_joined', 'last_login', 'profile', 'roles', 'version'}),
    'users': frozenset({'username', 'email', 'first_name', 'last_name', 'phone'}),
    'role': frozenset({'id', 'name', 'description', 'is_active', 'permissions', 'created_at', 'version'}),
    'roles': frozenset({'id', 'name', 'description', 'is_active', 'created_at'}),
    'post': frozenset({'id', 'code', 'name', 'description', 'order', 'is_active', 'version', 'created_at'}),
    'posts': frozenset({'code', 'name', 'description'}),
    'files': frozenset({'id', 'original_name', 'file_type', 'size', 'content_type', 'uploader__username', 'download_count', 'purpose', 'created_at'}),
    'logs': frozenset({'id', 'created_at', 'user__username', 'action', 'resource', 'resource_id', 'status', 'ip_address',
                       'username', 'level', 'request_method'}),
    'tasks': frozenset({'id', 'status', 'task_type', 'created_at', 'progress'}),
}

RESOURCE_ALIASES = {'users': 'user', 'roles': 'role', 'posts': 'post'}


def canonical_resource(resource):
    return RESOURCE_ALIASES.get(resource, resource)


def field_policy_registry():
    """只接纳显式模块契约；关闭模块保留角色配置语义，不扫描数据库模型。"""
    from apps.core.modules import MODULES
    from django.core.exceptions import ImproperlyConfigured
    result = dict(FIELD_POLICY_FIELDS)
    for module in MODULES:
        for resource, fields in module.field_policies:
            if resource in result:
                raise ImproperlyConfigured('字段权限资源重复：' + resource)
            result[resource] = frozenset(fields)
    return result


def validate_field_permissions(value):
    """验证角色字段策略并返回去重后的规范化副本。"""
    from apps.core.error_i18n import error_text
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError({'field_permissions': '字段策略必须是对象'})
    result = {}
    registry = field_policy_registry()
    for raw_resource, raw_policy in value.items():
        resource = canonical_resource(raw_resource)
        allowed = registry.get(resource)
        if allowed is None or raw_resource != resource:
            raise ValidationError({'field_permissions': error_text('不支持字段策略资源：{resource}', resource=raw_resource)})
        if not isinstance(raw_policy, Mapping) or set(raw_policy) - {'read', 'write'}:
            raise ValidationError({'field_permissions': error_text('{resource} 只允许 read/write 两类字段', resource=resource)})
        normalized = {}
        for action in ('read', 'write'):
            fields = raw_policy.get(action, [])
            if not isinstance(fields, list) or any(not isinstance(field, str) for field in fields):
                raise ValidationError({'field_permissions': error_text('{resource}.{action} 必须是字符串数组', resource=resource, action=action)})
            if len(fields) != len(set(fields)):
                raise ValidationError({'field_permissions': error_text('{resource}.{action} 不能重复', resource=resource, action=action)})
            unknown = set(fields) - allowed
            if unknown:
                raise ValidationError({'field_permissions': error_text('{resource}.{action} 含未知字段：{fields}', resource=resource, action=action, fields=sorted(unknown))})
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
    fields, _reason = resolve_field_policy(user, resource, action, _declared_policies(user, resource))
    return fields


def resolve_field_policy(user, resource, action, declared_policies):
    """请求授权与诊断共享组合规则；调用方可提供同次读取的角色策略快照。"""
    canonical = canonical_resource(resource)
    all_fields = field_policy_registry().get(canonical)
    if all_fields is None:
        raise ValueError(f'未登记字段策略资源：{resource}')
    if user and (user.is_superuser or user.is_staff):
        return set(all_fields), 'administrator'
    policies = [policy.get(canonical) for policy in declared_policies
                if isinstance(policy, Mapping) and canonical in policy]
    if not policies:
        return set(all_fields), 'legacy_unrestricted'
    return ({field for policy in policies if isinstance(policy, Mapping)
             for field in policy.get(action, []) if field in all_fields}, 'explicit_union')


def business_allowed_fields(user, resource, action):
    """未重新生成契约的旧模块保持原行为；登记后的模块统一走角色实时策略。"""
    if resource not in field_policy_registry():
        return None
    return allowed_fields(user, resource, action)


def enforce_write_fields(user, resource, fields, *, allow=()):
    allowed = allowed_fields(user, resource, 'write')
    blocked = set(fields) - set(allow) - allowed
    if blocked:
        from apps.core.error_i18n import error_text
        raise PermissionDenied(error_text('没有写入字段权限：{fields}', fields=', '.join(sorted(blocked))))


def filter_read_fields(user, resource, data):
    allowed = allowed_fields(user, resource, 'read')
    return {key: value for key, value in data.items() if key in allowed}
