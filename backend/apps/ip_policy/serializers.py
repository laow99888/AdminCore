import ipaddress
from rest_framework import serializers
from .models import IPPolicy


class NetworkListField(serializers.ListField):
    def __init__(self, **kwargs):
        super().__init__(child=serializers.CharField(max_length=80), max_length=100, **kwargs)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        try:
            networks = [ipaddress.ip_network(value, strict=False) for value in values]
        except ValueError:
            raise serializers.ValidationError('请输入有效的 IPv4、IPv6 或 CIDR') from None
        if any('%' in value for value in values):
            raise serializers.ValidationError('不允许带区域标识的 IP 地址')
        result = sorted(set(str(network) for network in networks))
        if len(result) != len(values):
            raise serializers.ValidationError('同一网络不能重复登记')
        return result


class IPPolicySerializer(serializers.ModelSerializer):
    allow = NetworkListField()
    deny = NetworkListField()
    version = serializers.IntegerField(min_value=1)
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=4096)

    class Meta:
        model = IPPolicy
        fields = ('enabled', 'allow', 'deny', 'version', 'updated_at', 'current_password')
        read_only_fields = ('updated_at',)
        extra_kwargs = {'enabled': {'required': True}}

    def validate(self, values):
        if set(self.initial_data) - {'enabled', 'allow', 'deny', 'version', 'current_password'}:
            raise serializers.ValidationError('只能提交登记的 IP 策略字段')
        return values


class PolicyPreviewSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    allow = NetworkListField()
    deny = NetworkListField()

    def validate(self, values):
        if set(self.initial_data) != {'enabled', 'allow', 'deny'}:
            raise serializers.ValidationError('预检只接受当前来源与策略配置')
        return values


class IPPolicyPreviewResultSerializer(serializers.Serializer):
    source_ip = serializers.CharField(allow_null=True)
    allowed = serializers.BooleanField()
