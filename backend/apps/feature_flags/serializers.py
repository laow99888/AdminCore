from django.contrib.auth import get_user_model
from rest_framework import serializers
from apps.permissions.models import Role
from .models import FeatureFlag


class FlagKeyField(serializers.RegexField):
    def __init__(self, **kwargs):
        super().__init__(r'^[a-z][a-z0-9_.-]{0,99}$', max_length=100, **kwargs)


class FeatureFlagSerializer(serializers.ModelSerializer):
    key = FlagKeyField()
    version = serializers.IntegerField(min_value=0, required=True)
    rollout = serializers.IntegerField(min_value=0, max_value=10000, required=False)
    included_users = serializers.ListField(child=serializers.UUIDField(), max_length=100, required=False)
    excluded_users = serializers.ListField(child=serializers.UUIDField(), max_length=100, required=False)
    roles = serializers.ListField(child=serializers.UUIDField(), max_length=100, required=False)

    class Meta:
        model = FeatureFlag
        fields = ('id', 'key', 'name', 'description', 'enabled', 'rollout', 'included_users',
                  'excluded_users', 'roles', 'version', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate(self, values):
        writable = set(self.fields) - set(self.Meta.read_only_fields)
        if set(self.initial_data) - writable:
            raise serializers.ValidationError('只能提交登记的开关字段')
        if 'version' not in values:
            raise serializers.ValidationError({'version': '必须提交读取到的版本'})
        if self.instance and 'key' in values and values['key'] != self.instance.key:
            raise serializers.ValidationError({'key': '开关标识创建后不可修改'})
        for field, model in [('included_users', get_user_model()), ('excluded_users', get_user_model()), ('roles', Role)]:
            if field not in values:
                continue
            ids = [str(value) for value in values[field]]
            if len(set(ids)) != len(ids) or model.objects.filter(pk__in=ids).count() != len(ids):
                raise serializers.ValidationError({field: '目标必须存在且不能重复'})
            values[field] = sorted(ids)
        included = values.get('included_users', self.instance.included_users if self.instance else [])
        excluded = values.get('excluded_users', self.instance.excluded_users if self.instance else [])
        if set(included) & set(excluded):
            raise serializers.ValidationError('同一用户不能同时包含和排除')
        return values


class VersionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class EvaluationRequestSerializer(serializers.Serializer):
    keys = serializers.ListField(child=FlagKeyField(), max_length=100, min_length=1)

    def validate(self, values):
        if set(self.initial_data) != {'keys'} or len(set(values['keys'])) != len(values['keys']):
            raise serializers.ValidationError('只能提交不重复的开关标识，不允许指定其他用户')
        return values


class EvaluationSerializer(serializers.Serializer):
    key = serializers.CharField()
    enabled = serializers.BooleanField()


class TargetQuerySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=['users', 'roles'])
    search = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    selected = serializers.CharField(max_length=3699, required=False, allow_blank=True, default='')

    def validate_selected(self, value):
        from uuid import UUID
        try:
            ids = [str(UUID(part)) for part in value.split(',')] if value else []
        except ValueError:
            raise serializers.ValidationError('选择目标无效') from None
        if len(ids) > 100 or len(set(ids)) != len(ids):
            raise serializers.ValidationError('最多选择100个不重复目标')
        return ids


class TargetSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
