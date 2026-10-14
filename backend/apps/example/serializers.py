from rest_framework import serializers
from apps.core.system_config import config_value
from .models import WorkItem


class WorkItemSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(min_value=0, required=True)
    creator_name = serializers.CharField(source='creator.username', read_only=True)

    class Meta:
        model = WorkItem
        fields = ('id', 'title', 'notes', 'status', 'priority', 'creator', 'creator_name', 'version', 'created_at', 'updated_at')
        read_only_fields = ('id', 'creator', 'created_at', 'updated_at')

    def validate(self, values):
        if set(self.initial_data) - {'title', 'notes', 'status', 'priority', 'version'}:
            raise serializers.ValidationError('只能提交登记的业务字段')
        if 'version' not in values:
            raise serializers.ValidationError({'version': '更新必须提交读取到的版本'})
        return values

    def validate_title(self, value):
        if len(value.strip()) > config_value('example.title_limit'):
            raise serializers.ValidationError('标题超过当前系统参数的长度限制')
        return value.strip()


class VersionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
