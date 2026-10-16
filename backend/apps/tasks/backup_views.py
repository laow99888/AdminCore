"""备份目录、宿主执行器状态和恢复请求 API。"""
import re
import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.reauthentication import require_recent_password
from apps.core.schema import envelope
from apps.permissions.permissions import HasPermission, IsAdmin

from .models import BackupPreflight, BackupRestoreRequest, BackupRunnerStatus
from .backup import available

STAMP = re.compile(r'^\d{8}-\d{6}$')


def ready_runner(*, lock=False):
    query = BackupRunnerStatus.objects.select_for_update() if lock else BackupRunnerStatus.objects
    row = query.filter(pk=1).first()
    if (not available() or row is None or row.state != 'idle' or not row.last_seen_at
            or row.last_seen_at < timezone.now() - timedelta(minutes=3)):
        raise ValidationError('备份功能未启用或宿主执行器未就绪')
    return row


class BackupRestoreSerializer(serializers.Serializer):
    preflight_id = serializers.UUIDField()
    confirmation = serializers.CharField(max_length=20, trim_whitespace=False)
    current_password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True)

    def validate_confirmation(self, value):
        if value != '恢复备份':
            raise ValidationError('请输入“恢复备份”确认')
        return value


class BackupArtifactSerializer(serializers.Serializer):
    timestamp = serializers.CharField()
    created_at = serializers.CharField()
    artifacts = serializers.ListField(child=serializers.JSONField())
    remote_copy = serializers.BooleanField()


class BackupStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    state = serializers.CharField()
    directory_label = serializers.CharField()
    stage = serializers.CharField()
    last_error = serializers.CharField()
    last_seen_at = serializers.DateTimeField(allow_null=True)
    artifacts = BackupArtifactSerializer(many=True)
    restore_requests = serializers.ListField(child=serializers.JSONField())


class BackupPreflightSerializer(serializers.Serializer):
    preflight_id = serializers.UUIDField()
    timestamp = serializers.CharField()
    artifacts = serializers.ListField(child=serializers.JSONField())
    remote_copy = serializers.BooleanField()
    runner_state = serializers.CharField()
    requires_confirmation = serializers.BooleanField()


class BackupRestoreResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    timestamp = serializers.CharField()
    status = serializers.CharField()
    error = serializers.CharField(required=False)
    created_at = serializers.DateTimeField(required=False)
    completed_at = serializers.DateTimeField(allow_null=True, required=False)


def status_data():
    from django.conf import settings
    row = BackupRunnerStatus.objects.filter(pk=1).first()
    if row is None:
        state, label, stage, error, seen, artifacts = 'offline', '', '', '', None, []
    else:
        state, label, stage, error, seen, artifacts = row.state, row.directory_label, row.stage, row.last_error, row.last_seen_at, row.artifacts
        if not seen or seen < timezone.now() - timedelta(minutes=3):
            state = 'offline'
    requests = list(BackupRestoreRequest.objects.order_by('-created_at')[:20])
    receipts = {item['id']: item for item in (row.restore_receipts if row else [])}
    for item in requests:
        receipts.setdefault(str(item.pk), {'id': str(item.pk), 'timestamp': item.timestamp,
            'status': item.status, 'error': item.error, 'created_at': item.created_at.isoformat(),
            'completed_at': item.completed_at.isoformat() if item.completed_at else None})
    return {'enabled': bool(settings.ADMINCORE_BACKUP_ENABLED), 'state': state,
            'directory_label': label, 'stage': stage, 'last_error': error,
            'last_seen_at': seen, 'artifacts': artifacts,
            'restore_requests': sorted(receipts.values(), key=lambda item: item['created_at'], reverse=True)[:20]}


class BackupStatusView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'backup:read'

    @extend_schema(responses=envelope('BackupStatusResponse', BackupStatusSerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': BackupStatusSerializer(status_data()).data},
                        headers={'Cache-Control': 'private, no-store'})


class BackupPreflightView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'backup:restore'

    @extend_schema(request=None, responses=envelope('BackupPreflightResponse', BackupPreflightSerializer()))
    def post(self, request, timestamp):
        if not STAMP.fullmatch(timestamp):
            raise NotFound()
        row = ready_runner()
        item = next((item for item in (row.artifacts if row else []) if item.get('timestamp') == timestamp), None)
        if item is None:
            raise NotFound('备份不存在或尚未由宿主执行器校验')
        if not isinstance(item.get('artifacts'), list) or len(item['artifacts']) != 3:
            raise ValidationError('备份索引不完整，请重新运行宿主执行器')
        preflight = BackupPreflight.objects.create(timestamp=timestamp, actor=request.user,
            artifact_digest=hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=15))
        return Response({'code': 200, 'message': '预检通过', 'data': {
            'preflight_id': str(preflight.pk), 'timestamp': timestamp,
            'artifacts': item['artifacts'], 'remote_copy': item['remote_copy'],
            'runner_state': status_data()['state'], 'requires_confirmation': True,
        }})


class BackupRestoreView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'backup:restore'

    @extend_schema(request=BackupRestoreSerializer, responses={202: envelope('BackupRestoreAcceptedResponse', BackupRestoreResultSerializer())})
    def post(self, request, timestamp):
        if not STAMP.fullmatch(timestamp):
            raise NotFound()
        serializer = BackupRestoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            actor = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
            session = require_recent_password(request, actor, 'backup:restore')
            row = ready_runner(lock=True)
            item = next((item for item in (row.artifacts if row else []) if item.get('timestamp') == timestamp), None)
            if item is None:
                raise NotFound('备份不存在或尚未由宿主执行器校验')
            preflight = BackupPreflight.objects.filter(pk=serializer.validated_data['preflight_id'], actor=actor,
                timestamp=timestamp, expires_at__gt=timezone.now()).first()
            if preflight is None or preflight.artifact_digest != hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest():
                raise ValidationError('预检已过期或备份目录发生变化，请重新预检')
            if BackupRestoreRequest.objects.filter(preflight_id=preflight.pk).exists():
                raise ValidationError('该预检已使用，请重新预检')
            if BackupRestoreRequest.objects.filter(status__in=['pending', 'running']).exists():
                raise ValidationError('已有恢复请求正在执行')
            restore = BackupRestoreRequest.objects.create(timestamp=timestamp,
                preflight_id=preflight.pk, requested_by=actor, session_version=actor.session_version,
                session_id=session.pk if session else None, artifact_digest=preflight.artifact_digest)
            from apps.logs.audit import write_audit
            write_audit(request=request, actor=actor, resource='backup_restore', identifier=restore.pk,
                action='create', after={'timestamp': timestamp, 'status': restore.status, 'preflight_id': preflight.pk})
        return Response({'code': 202, 'message': '恢复请求已登记，宿主执行器将停写并切换数据库；结果可能需要恢复后人工核对',
                         'data': {'id': str(restore.pk), 'timestamp': restore.timestamp, 'status': restore.status}}, status=status.HTTP_202_ACCEPTED)


class BackupRestoreRequestView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'backup:read'

    @extend_schema(responses=envelope('BackupRestoreRequestResponse', BackupRestoreResultSerializer()))
    def get(self, request, request_id):
        row = BackupRestoreRequest.objects.filter(pk=request_id).first()
        if row is None:
            raise NotFound()
        return Response({'code': 200, 'message': 'success', 'data': {
            'id': str(row.pk), 'timestamp': row.timestamp, 'status': row.status,
            'error': row.error, 'created_at': row.created_at, 'completed_at': row.completed_at,
        }}, headers={'Cache-Control': 'private, no-store'})
