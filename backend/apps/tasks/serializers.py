"""
任务调度序列化器
"""

from rest_framework import serializers

from .models import TaskRecord


class TaskRecordSerializer(serializers.ModelSerializer):
    """任务记录序列化"""
    creator_name = serializers.CharField(source='creator.username', read_only=True, default=None)
    duration = serializers.SerializerMethodField()
    execution = serializers.SerializerMethodField()
    request_id = serializers.SerializerMethodField()

    class Meta:
        model = TaskRecord
        fields = [
            'id', 'name', 'task_type', 'status', 'celery_task_id', 'progress',
            'result', 'error', 'related_resource', 'creator', 'creator_name',
            'started_at', 'completed_at', 'duration', 'created_at', 'execution', 'request_id',
        ]
        read_only_fields = fields

    def get_request_id(self, obj) -> str:
        row = getattr(obj, 'import_execution', None) or getattr(obj, 'maintenance_request', None)
        return row.request_id if row else ''

    def get_duration(self, obj) -> float | None:
        """执行耗时（秒），未完成任务返回 None"""
        if obj.started_at and obj.completed_at:
            return round((obj.completed_at - obj.started_at).total_seconds(), 2)
        return None

    def get_execution(self, obj) -> dict | None:
        row = getattr(obj, 'import_execution', None)
        if row is None:
            maintenance = getattr(obj, 'maintenance_request', None)
            return {'attempt': 1, 'policy': maintenance.policy, 'can_resume': False,
                    'semantics': 'new_preview_required'} if maintenance else None
        return {'attempt': row.attempt, 'policy': row.policy,
                'can_resume': obj.status in ('failed', 'cancelled') and row.attempt < 5
                              and row.batch.active_record_id == obj.pk,
                'semantics': 'resume_uncommitted_rows'}
