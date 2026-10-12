"""
任务调度序列化器
"""

from rest_framework import serializers

from .models import TaskRecord


class TaskRecordSerializer(serializers.ModelSerializer):
    """任务记录序列化"""
    creator_name = serializers.CharField(source='creator.username', read_only=True, default=None)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = TaskRecord
        fields = [
            'id', 'name', 'task_type', 'status', 'celery_task_id', 'progress',
            'result', 'error', 'related_resource', 'creator', 'creator_name',
            'started_at', 'completed_at', 'duration', 'created_at',
        ]
        read_only_fields = fields

    def get_duration(self, obj):
        """执行耗时（秒），未完成任务返回 None"""
        if obj.started_at and obj.completed_at:
            return round((obj.completed_at - obj.started_at).total_seconds(), 2)
        return None
