"""写入协议拒绝未知字段和重复表单键。"""
from collections.abc import Mapping
from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['请求包含未注册字段']})
        if hasattr(data, 'getlist') and any(len(data.getlist(key)) != 1 for key in data):
            raise serializers.ValidationError({'non_field_errors': ['字段不能重复']})
        return super().to_internal_value(data)
