"""只管理注册的两项维护计划；核心可靠派发不开放启停。"""
import hashlib
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from celery.schedules import crontab
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.events import enqueue_event
from apps.core.idempotency import with_idempotency
from apps.core.modules import task_enabled
from apps.core.schema import envelope
from apps.core.system_views import VersionConflict, audit
from apps.permissions.permissions import HasPermission, IsAdmin
from .maintenance import JOBS, valid_preview, validate_options
from .models import MaintenanceRequest, TaskRecord
from .serializers import TaskRecordSerializer


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError({'non_field_errors': ['请求包含未注册字段']})
        return super().to_internal_value(data)


class ScheduleWriteSerializer(StrictSerializer):
    revision = serializers.CharField(max_length=64)
    enabled = serializers.BooleanField()
    minute = serializers.CharField(max_length=64)
    hour = serializers.CharField(max_length=64)
    day_of_week = serializers.CharField(max_length=64)
    day_of_month = serializers.CharField(max_length=64)
    month_of_year = serializers.CharField(max_length=64)
    timezone = serializers.CharField(max_length=64)
    options = serializers.JSONField(default=dict)

    def validate(self, data):
        try:
            ZoneInfo(data['timezone'])
            cron = {key: data[key] for key in ['minute', 'hour', 'day_of_week', 'day_of_month', 'month_of_year']}
            if any(not re.fullmatch(r'[0-9*,/\-]+', value) for value in cron.values()):
                raise ValueError()
            crontab(**cron)
        except (ValueError, KeyError, ZoneInfoNotFoundError) as exc:
            raise ValidationError('Cron 表达式或时区不合法') from exc
        if type(self.initial_data.get('enabled')) is not bool:
            raise ValidationError('enabled 必须为布尔值')
        data['options'] = validate_options(self.context['key'], data['options'])
        return data


class ScheduleRunSerializer(StrictSerializer):
    revision = serializers.CharField(max_length=64)
    options = serializers.JSONField()
    confirmation = serializers.CharField(required=False, allow_blank=True)
    preview_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_options(self, value):
        return validate_options(self.context['key'], value)


class ScheduleRowSerializer(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField()
    task = serializers.CharField()
    enabled = serializers.BooleanField()
    module_enabled = serializers.BooleanField()
    missing = serializers.BooleanField()
    revision = serializers.CharField()
    cron = serializers.JSONField()
    options = serializers.JSONField()
    supported = serializers.BooleanField()
    overlap = serializers.CharField()
    time_limit_seconds = serializers.IntegerField()
    preview = serializers.JSONField(allow_null=True)
    last_run = TaskRecordSerializer(allow_null=True)


def configuration(row):
    if row is None:
        return None
    cron = row.crontab
    return {'task': row.task, 'enabled': row.enabled, 'args': row.args, 'kwargs': row.kwargs,
            'cron': {'minute': cron.minute, 'hour': cron.hour, 'day_of_week': cron.day_of_week,
                     'day_of_month': cron.day_of_month, 'month_of_year': cron.month_of_year,
                     'timezone': str(cron.timezone)} if cron else None,
            **{field: str(getattr(row, field)) for field in ['interval_id', 'solar_id', 'clocked_id',
               'one_off', 'start_time', 'expires', 'expire_seconds', 'queue', 'exchange', 'routing_key', 'headers', 'priority']}}


def revision(row):
    return hashlib.sha256(json.dumps(configuration(row), sort_keys=True).encode()).hexdigest() if row else '0'


def schedule_row(key, user):
    job = JOBS[key]
    row = PeriodicTask.objects.select_related('crontab').filter(name=job['schedule']).first()
    supported = True
    try:
        options = validate_options(key, json.loads(row.kwargs)) if row else validate_options(key, {})
        if row and (row.task != job['task'] or json.loads(row.args) != []):
            supported = False
    except (ValueError, ValidationError):
        options, supported = {}, False
    last = TaskRecord.objects.filter(related_resource='maintenance:' + key).order_by('-created_at').first()
    preview = MaintenanceRequest.objects.select_related('record').filter(
        key=key, record__creator=user, options__dry_run=True, record__status='success',
    ).order_by('-record__completed_at').first()
    preview_data = {'id': str(preview.pk), 'result': preview.record.result,
                    'completed_at': preview.record.completed_at.isoformat()} if preview and valid_preview(key, preview.pk, user.pk) else None
    return {'key': key, 'name': job['name'], 'task': job['task'], 'enabled': bool(row and row.enabled),
            'module_enabled': task_enabled(job['task']), 'missing': row is None, 'revision': revision(row),
            'cron': configuration(row)['cron'] if row and row.crontab else {
                'minute': '0' if key == 'files' else '15', 'hour': '3', 'day_of_week': '*',
                'day_of_month': '*', 'month_of_year': '*', 'timezone': settings.TIME_ZONE},
            'options': options, 'supported': supported, 'overlap': 'skip', 'time_limit_seconds': 300,
            'preview': preview_data, 'last_run': TaskRecordSerializer(last).data if last else None}


class ScheduleView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    permission_map = {'get': 'schedule:read', 'patch': 'schedule:update'}

    def job(self, key):
        if key not in JOBS:
            raise NotFound()
        return JOBS[key]

    @extend_schema(responses=envelope('MaintenanceSchedulesResponse', ScheduleRowSerializer(many=True)))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': [schedule_row(key, request.user) for key in JOBS]})

    @extend_schema(request=ScheduleWriteSerializer, responses=envelope('MaintenanceScheduleUpdatedResponse', ScheduleRowSerializer()))
    def patch(self, request, key):
        job = self.job(key)
        serializer = ScheduleWriteSerializer(data=request.data, context={'key': key})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not task_enabled(job['task']):
            raise ValidationError('任务依赖模块未启用')
        try:
            with transaction.atomic():
                row = PeriodicTask.objects.select_for_update().filter(name=job['schedule']).first()
                if data['revision'] != revision(row):
                    raise VersionConflict()
                if row and (row.task != job['task'] or not schedule_row(key, request.user)['supported']):
                    raise ValidationError('现有计划与注册定义不一致，请通过管理命令修复')
                before = configuration(row)
                cron, _ = CrontabSchedule.objects.get_or_create(**{field: data[field] for field in
                    ['minute', 'hour', 'day_of_week', 'day_of_month', 'month_of_year', 'timezone']})
                row = row or PeriodicTask(name=job['schedule'], task=job['task'])
                row.enabled, row.crontab = data['enabled'], cron
                if not before or before['cron'] != configuration(row)['cron']:
                    row.last_run_at = None
                row.interval, row.solar, row.clocked = None, None, None
                row.args, row.kwargs = '[]', json.dumps(data['options'])
                row.one_off = False
                row.start_time, row.expires, row.expire_seconds = None, None, None
                row.save()
                public_fields = ('task', 'enabled', 'cron', 'kwargs')
                audit(request, 'maintenance_schedule', key,
                      {field: before[field] for field in public_fields} if before else None,
                      {field: configuration(row)[field] for field in public_fields})
        except IntegrityError as exc:
            raise VersionConflict() from exc
        return Response({'code': 200, 'message': 'success', 'data': schedule_row(key, request.user)})


class ScheduleRunView(ScheduleView):
    permission_map = {'post': 'schedule:run'}
    http_method_names = ['post', 'options']

    @extend_schema(request=ScheduleRunSerializer, responses={202: envelope('MaintenanceAcceptedResponse', TaskRecordSerializer())})
    def post(self, request, key):
        job = self.job(key)
        serializer = ScheduleRunSerializer(data=request.data, context={'key': key})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not request.headers.get('Idempotency-Key'):
            raise ValidationError('手动执行必须提供 Idempotency-Key')
        if not task_enabled(job['task']):
            raise ValidationError('任务依赖模块未启用')
        if not PeriodicTask.objects.filter(task='core.dispatch_outbox', enabled=True).exists():
            raise ValidationError('可靠事件补偿计划未启用，不能提交维护任务')
        def submit():
            row = PeriodicTask.objects.select_for_update().filter(name=job['schedule']).first()
            if data['revision'] != revision(row):
                raise VersionConflict()
            if not schedule_row(key, request.user)['supported']:
                raise ValidationError('计划参数与注册定义不一致')
            if not data['options']['dry_run']:
                if data.get('confirmation') != '执行清理' or not valid_preview(key, data.get('preview_id'), request.user.pk):
                    raise ValidationError('执行前需要 15 分钟内的有效预览与确认；策略变化后需重新预览')
            record = TaskRecord.objects.create(name=job['name'], task_type='cleanup', creator=request.user,
                                               related_resource='maintenance:' + key)
            MaintenanceRequest.objects.create(record=record, key=key, options=data['options'],
                session_version=request.user.session_version, request_id=str(getattr(request, 'request_id', ''))[:100],
                preview_id=data.get('preview_id'))
            audit(request, 'maintenance_run', record.pk, None, {'key': key, 'options': data['options'],
                  'preview_id': str(data.get('preview_id') or ''), 'request_id': str(getattr(request, 'request_id', ''))})
            enqueue_event('maintenance.requested', 'maintenance:' + str(record.pk), {'record_id': str(record.pk)}, request)
            return Response({'code': 202, 'message': '已登记，等待任务中心执行', 'data': TaskRecordSerializer(record).data}, status=202)
        return with_idempotency(request, 'maintenance:' + key, submit)
