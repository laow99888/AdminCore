import re
from rest_framework import serializers
from .models import DataDictionary


class ConfigWriteSerializer(serializers.Serializer):
    value = serializers.JSONField()
    version = serializers.IntegerField(min_value=0)


class ConfigRowSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    kind = serializers.CharField()
    value = serializers.JSONField()
    default = serializers.JSONField()
    version = serializers.IntegerField()
    minimum = serializers.IntegerField()
    maximum = serializers.IntegerField()
    effective = serializers.CharField()


class DictionarySerializer(serializers.ModelSerializer):
    # 0 只用于新建；更新时必须回传当前版本。
    version = serializers.IntegerField(min_value=0, required=True)

    class Meta:
        model = DataDictionary
        fields = ('id', 'code', 'name', 'description', 'is_active', 'items', 'version', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_code(self, value):
        if self.instance and value != self.instance.code:
            raise serializers.ValidationError('已创建的字典编码不可修改，请新建字典并迁移引用')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', value):
            raise serializers.ValidationError('编码仅允许小写字母、数字和下划线，且以字母开头')
        if value in {'approval_status', 'task_status'}:
            raise serializers.ValidationError('状态机枚举不能作为业务字典编辑')
        return value

    def validate_items(self, value):
        if not isinstance(value, list) or len(value) > 500:
            raise serializers.ValidationError('最多允许 500 个字典项')
        seen = set()
        result = []
        for item in value:
            if not isinstance(item, dict) or set(item) - {'label', 'value', 'is_active', 'order'}:
                raise serializers.ValidationError('字典项只允许 label、value、is_active、order')
            label, code = item.get('label'), item.get('value')
            if not isinstance(label, str) or not 1 <= len(label.strip()) <= 100:
                raise serializers.ValidationError('字典项名称长度必须为 1–100')
            if not isinstance(code, str) or not 1 <= len(code) <= 100 or code in seen:
                raise serializers.ValidationError('字典项值必须为不重复的 1–100 字符文本')
            active, order = item.get('is_active', True), item.get('order', 0)
            if type(active) is not bool or type(order) is not int or not 0 <= order <= 100000:
                raise serializers.ValidationError('启用状态必须为布尔值，排序必须为 0–100000 的整数')
            seen.add(code)
            result.append({'label': label.strip(), 'value': code, 'is_active': active, 'order': order})
        return sorted(result, key=lambda item: item['order'])


class DictionaryOptionsSerializer(serializers.Serializer):
    code = serializers.CharField()
    version = serializers.IntegerField()
    items = serializers.JSONField()


class BrandSerializer(serializers.Serializer):
    name = serializers.CharField()
    tagline = serializers.CharField()
    logo = serializers.CharField(allow_blank=True)
