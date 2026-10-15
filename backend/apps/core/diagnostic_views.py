from django.core.cache.backends.locmem import LocMemCache
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.permissions.permissions import HasPermission, IsAdmin
from .diagnostics import resource_snapshot, system_information
from .schema import envelope


class DiagnosticThrottle(UserRateThrottle):
    """本进程限速，避免 Redis 故障阻止读取诊断；不是全局安全配额。"""
    cache = LocMemCache('admincore-diagnostics', {'OPTIONS': {'MAX_ENTRIES': 1024}})
    rate = '30/min'
    scope = 'diagnostics'


class DependencySerializer(serializers.Serializer):
    name = serializers.CharField()
    version = serializers.CharField(allow_null=True)


class ServiceSerializer(DependencySerializer):
    status = serializers.ChoiceField(choices=['ok', 'unavailable', 'in_process', 'disabled'])
    latency_ms = serializers.FloatField(allow_null=True)


class QueueMetricSerializer(serializers.Serializer):
    counts = serializers.DictField(child=serializers.IntegerField(), allow_null=True)
    oldest_pending_seconds = serializers.FloatField(allow_null=True)
    oldest_failed_seconds = serializers.FloatField(allow_null=True)


class NotificationMetricSerializer(QueueMetricSerializer):
    status = serializers.ChoiceField(choices=['ok', 'unavailable', 'disabled'])


class LostCandidateSerializer(serializers.Serializer):
    pending = serializers.IntegerField()
    running = serializers.IntegerField()
    sampled = serializers.IntegerField()
    unclassified = serializers.IntegerField()
    truncated = serializers.BooleanField()


class DurationMetricSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    average = serializers.FloatField(allow_null=True)
    p95 = serializers.FloatField(allow_null=True)
    max = serializers.FloatField(allow_null=True)


class TaskRecordMetricSerializer(serializers.Serializer):
    counts = serializers.DictField(child=serializers.IntegerField(), allow_null=True)
    lost_candidates = LostCandidateSerializer(allow_null=True)
    duration_seconds = DurationMetricSerializer(allow_null=True)


class BrokerMetricSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['ok', 'unavailable', 'disabled'])
    ready = serializers.IntegerField(allow_null=True)


class CorrelationMetricSerializer(serializers.Serializer):
    outbox_request_linked = serializers.IntegerField(allow_null=True)
    task_request_linked = serializers.IntegerField(allow_null=True)
    notification_request_linked = serializers.IntegerField(allow_null=True)


class TaskMetricSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['ok', 'degraded', 'disabled'])
    task_records = TaskRecordMetricSerializer()
    outbox = QueueMetricSerializer()
    notifications = NotificationMetricSerializer()
    broker = BrokerMetricSerializer()
    correlation = CorrelationMetricSerializer()


class InformationSerializer(serializers.Serializer):
    sampled_at = serializers.DateTimeField()
    python = serializers.CharField()
    os = serializers.CharField()
    architecture = serializers.CharField()
    environment = serializers.CharField()
    debug = serializers.BooleanField()
    preset = serializers.CharField()
    modules = serializers.ListField(child=serializers.CharField())
    timezone = serializers.CharField()
    database = serializers.CharField()
    storage = serializers.CharField()
    dependencies = DependencySerializer(many=True)
    services = ServiceSerializer(many=True)
    task_metrics = TaskMetricSerializer()


class CpuSerializer(serializers.Serializer):
    capacity_cores = serializers.FloatField(allow_null=True)
    percent = serializers.FloatField(allow_null=True)
    sample_seconds = serializers.FloatField(allow_null=True)


class MemorySerializer(serializers.Serializer):
    used_bytes = serializers.IntegerField(allow_null=True)
    total_bytes = serializers.IntegerField(allow_null=True)
    percent = serializers.FloatField(allow_null=True)


class DiskSerializer(MemorySerializer):
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=['ok', 'unavailable'])
    free_bytes = serializers.IntegerField(allow_null=True)


class ProcessSerializer(serializers.Serializer):
    pid = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=['python', 'other'])
    state = serializers.CharField()
    cpu_seconds = serializers.FloatField()
    rss_bytes = serializers.IntegerField()
    uptime_seconds = serializers.FloatField()


class MonitorSerializer(serializers.Serializer):
    sampled_at = serializers.DateTimeField()
    scope = serializers.ChoiceField(choices=['container', 'host'])
    cpu = CpuSerializer()
    memory = MemorySerializer()
    disks = DiskSerializer(many=True)
    processes = ProcessSerializer(many=True)
    processes_truncated = serializers.BooleanField()
    processes_supported = serializers.BooleanField()


class InformationView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'diagnostics:read'
    throttle_classes = [DiagnosticThrottle]
    http_method_names = ['get', 'head', 'options']

    @extend_schema(responses=envelope('SystemInformationResponse', InformationSerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': system_information()},
                        headers={'Cache-Control': 'private, no-store'})


class MonitorView(InformationView):
    required_permission = 'monitor:read'

    @extend_schema(responses=envelope('SystemMonitorResponse', MonitorSerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': resource_snapshot()},
                        headers={'Cache-Control': 'private, no-store'})
