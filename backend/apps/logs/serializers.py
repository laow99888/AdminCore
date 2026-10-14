"""
日志序列化器
"""

from rest_framework import serializers
from .models import OperationLog, LoginLog, ExceptionLog


class OperationLogSerializer(serializers.ModelSerializer):
    """操作日志序列化器"""
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = OperationLog
        fields = ('id', 'username', 'action', 'resource', 'resource_id', 'description', 'ip_address', 'status', 'created_at',
                  'actor_identifier', 'request_id', 'task_id', 'task_record_id', 'audit_version',
                  'before_values', 'after_values', 'batch_results')
        read_only_fields = fields


class OperationLogListSerializer(OperationLogSerializer):
    """结构化大字段按需在详情读取，避免分页响应重复携带。"""
    class Meta(OperationLogSerializer.Meta):
        fields = tuple(field for field in OperationLogSerializer.Meta.fields
                       if field not in ('before_values', 'after_values', 'batch_results'))
        read_only_fields = fields


class LoginLogSerializer(serializers.ModelSerializer):
    """登录日志序列化器"""
    class Meta:
        model = LoginLog
        fields = ('id', 'username', 'status', 'ip_address', 'error_message', 'created_at')
        read_only_fields = ('id', 'created_at')


class ExceptionLogSerializer(serializers.ModelSerializer):
    """异常日志序列化器"""
    username = serializers.CharField(source='user.username', read_only=True, allow_null=True)

    class Meta:
        model = ExceptionLog
        fields = ('id', 'level', 'message', 'username', 'ip_address', 'request_path', 'request_method', 'created_at')
        read_only_fields = ('id', 'created_at')
