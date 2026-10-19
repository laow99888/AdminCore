"""单次列表序列化的权限快照，不能用于写入授权或跨请求缓存。"""
from .permissions import permission_codes
from .field_permissions import _declared_policies, field_policy_registry, resolve_field_policy


class ReadPermissionSnapshot:
    def __init__(self, actor):
        self.actor = actor
        self.codes = set(permission_codes(actor))
        self.policies = _declared_policies(actor, '')

    def can(self, code):
        return bool(self.actor.is_active and ('*' in self.codes or code in self.codes))

    def fields(self, resource):
        if resource not in field_policy_registry():
            return None
        return resolve_field_policy(self.actor, resource, 'read', self.policies)[0]
