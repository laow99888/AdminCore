"""请求租户范围内的显式关联字段。"""
from rest_framework import serializers

from .tenancy import TenantQuerysetMixin


class TenantPrimaryKeyRelatedField(TenantQuerysetMixin, serializers.PrimaryKeyRelatedField):
    """显式声明的 QuerySet 与自动生成字段一样，在校验时应用当前租户。"""
