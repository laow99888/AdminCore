"""业务唯一字段按显式租户验证；数据库约束负责最终并发裁决。"""
from rest_framework.validators import UniqueValidator
from .tenancy import current_tenant_id, enabled


class TenantUniqueSerializerMixin:
    tenant_unique_fields = ()

    def get_fields(self):
        fields = super().get_fields()
        tenant = current_tenant_id() if enabled() else None
        for name in self.tenant_unique_fields:
            fields[name].validators = [v for v in fields[name].validators if not isinstance(v, UniqueValidator)]
            fields[name].validators.append(UniqueValidator(
                queryset=self.Meta.model.all_objects.filter(tenant_id=tenant), message='当前租户中该值已存在'))
        return fields

    def get_validators(self):
        # 含 tenant 的条件约束由数据库及上述逐字段校验共同保证；tenant 不接受客户端输入。
        return []
