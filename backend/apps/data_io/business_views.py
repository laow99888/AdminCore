"""显式业务资源的映射、单表/整单预检、确认与错误下载。"""
import csv
import io
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes, OpenApiParameter
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.query_budget import query_budget
from apps.core.schema import envelope, MessageResponse
from apps.files.models import FileModel
from apps.tasks.models import TaskRecord
from apps.tasks.reliability import authorize
from apps.tasks.serializers import TaskRecordSerializer
from . import business
from .execution import register, ExecutionConflict
from .models import ImportMapping, BusinessImportPlan
from .views import DataModuleView, spreadsheet_text, _log


class BusinessUploadSerializer(serializers.Serializer):
    resource = serializers.RegexField(r'^[a-z][a-z0-9_]{0,19}$')
    file = serializers.FileField()


class BusinessPreviewSerializer(BusinessUploadSerializer):
    options = serializers.JSONField()


class BusinessMappingSerializer(serializers.Serializer):
    resource = serializers.RegexField(r'^[a-z][a-z0-9_]{0,19}$')
    name = serializers.CharField(max_length=80)
    options = serializers.JSONField()


class BusinessFieldSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    kind = serializers.CharField()
    required = serializers.BooleanField()
    key = serializers.BooleanField()


class BusinessCatalogSerializer(serializers.Serializer):
    fields = BusinessFieldSerializer(many=True)
    modes = serializers.ListField(child=serializers.CharField())
    max_rows = serializers.IntegerField()
    max_bytes = serializers.IntegerField()
    structure = serializers.CharField()
    exportable = serializers.BooleanField()


class BusinessInspectSerializer(serializers.Serializer):
    headers = serializers.ListField(child=serializers.CharField())
    rows = serializers.IntegerField()


class BusinessRowErrorSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    message = serializers.CharField()


class BusinessPreviewResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    summary = serializers.DictField(child=serializers.IntegerField())
    expires_at = serializers.DateTimeField()
    errors = BusinessRowErrorSerializer(many=True)


class BusinessMappingResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    options = serializers.JSONField()


def response(data, status=200):
    return Response({'code': status, 'message': 'success', 'data': data}, status=status)


@extend_schema_view(get=extend_schema(parameters=[OpenApiParameter('resource', str)], responses=envelope('BusinessCatalogResponse', BusinessCatalogSerializer())))
class BusinessCatalogView(DataModuleView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        resource = request.query_params.get('resource', '')
        fields = business.catalog(request.user, resource)
        schema, _, _ = business.resource_schema(resource)
        from apps.permissions.permissions import has_permission_code
        return response({'fields': fields, 'modes': ['create', 'skip'] +
            (['update'] if has_permission_code(request.user, resource + ':update') else []),
            'max_rows': business.MAX_ROWS, 'max_bytes': business.MAX_BYTES,
            'structure': schema['structure'], 'exportable': True})


@extend_schema_view(post=extend_schema(request=BusinessUploadSerializer, responses=envelope('BusinessInspectResponse', BusinessInspectSerializer())))
class BusinessInspectView(DataModuleView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BusinessUploadSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        resource = serializer.validated_data['resource']
        business.require(request.user, resource)
        _, (headers, rows) = business.parse_upload(serializer.validated_data['file'])
        return response({'headers': headers, 'rows': len(rows)})


@extend_schema_view(post=extend_schema(request=BusinessPreviewSerializer, responses=envelope('BusinessPreviewResponse', BusinessPreviewResultSerializer())))
class BusinessPreviewView(DataModuleView):
    permission_classes = [IsAuthenticated]

    @query_budget()
    def post(self, request):
        serializer = BusinessPreviewSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        business.require(request.user, values['resource'])
        raw, (headers, rows) = business.parse_upload(values['file'])
        source = None
        try:
            with transaction.atomic():
                actor = authorize(request, 'data_io:import')
                options = business.options_for(actor, values['resource'], values['options'], headers)
                # 未提交且未过期的预检数量有界，防止无确认上传无限堆积。
                if BusinessImportPlan.objects.filter(creator=actor, submitted_at=None, expires_at__gt=timezone.now()).count() >= 20:
                    raise ValidationError('待确认预检最多20份，请等待过期或使用已有预检')
                planned, summary = business.preflight(actor, values['resource'], rows, options)
                from django.core.files.base import ContentFile
                from pathlib import Path
                name = Path(values['file'].name).name
                source = FileModel.objects.create(original_name=name, file=ContentFile(raw, name=name),
                    size=len(raw), file_type=name.rsplit('.', 1)[-1].lower(), uploader=actor, purpose='import')
                schema, _, _ = business.resource_schema(values['resource'])
                plan = BusinessImportPlan.objects.create(creator=actor, resource=values['resource'], source=source,
                    source_sha256=business.hashlib.sha256(raw).hexdigest(), summary=summary,
                    options={**options, 'rows': planned, 'schema_digest': business.schema_digest(schema), 'version': 2,
                             **({'source_row_count': len(rows)} if schema['structure'] == 'master_detail' else {})},
                    expires_at=timezone.now() + timedelta(hours=1))
                _log(request, 'create', '业务导入预检（未写业务记录）', str(plan.pk))
        except Exception:
            if source is not None and source.file:
                source.file.delete(save=False)
            raise
        return response({'id': str(plan.pk), 'summary': summary, 'expires_at': plan.expires_at,
                         'errors': [{'row': item['row'], 'message': item['error']} for item in planned if item['error']][:100]})


@extend_schema_view(post=extend_schema(request=None, responses=envelope('BusinessSubmitResponse', TaskRecordSerializer())))
class BusinessSubmitView(DataModuleView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, plan_id):
        actor = authorize(request, 'data_io:import')
        from apps.files.access import file_queryset_for_actor
        original = BusinessImportPlan.objects.filter(pk=plan_id, creator=actor).first()
        if original is None:
            raise NotFound()
        # 与保留策略及接续接口使用相同的源文件→批次/预检锁顺序。
        source = file_queryset_for_actor(FileModel.objects.select_for_update().filter(is_deleted=False), actor).filter(pk=original.source_id).first()
        plan = BusinessImportPlan.objects.select_for_update().filter(pk=plan_id, creator=actor).first()
        if plan is None:
            raise NotFound()
        schema, _, _ = business.require(actor, plan.resource, plan.options['mode'])
        business.options_for(actor, plan.resource, {key: plan.options[key] for key in ('mapping', 'key', 'mode')})
        if plan.submitted_at:
            if plan.record is None:
                raise ExecutionConflict()
            return response(TaskRecordSerializer(plan.record).data)
        if plan.expires_at <= timezone.now() or source is None or not source.file:
            raise ValidationError('预检已过期或源文件不可用，请重新预检')
        if business.schema_digest(schema) != plan.options['schema_digest']:
            raise ValidationError('业务定义已变化，请重新预检')
        record = TaskRecord.objects.create(name='导入' + schema['title'], task_type='import',
            related_resource=plan.resource, creator=actor, result={'file_id': str(plan.source_id), 'total': plan.summary['total']})
        execution = register(record, source, request)
        if execution.batch.source_sha256 != plan.source_sha256:
            raise ValidationError('预检源文件发生变化，请重新预检')
        execution.batch.options = plan.options
        execution.batch.save(update_fields=['options', 'updated_at'])
        plan.submitted_at, plan.record = timezone.now(), record
        plan.save(update_fields=['submitted_at', 'record', 'updated_at'])
        _log(request, 'create', '确认业务导入批次', str(record.pk))
        return response(TaskRecordSerializer(record).data)


@extend_schema_view(
    get=extend_schema(parameters=[OpenApiParameter('resource', str)], responses=envelope('BusinessMappingListResponse', BusinessMappingResultSerializer(many=True))),
    post=extend_schema(request=BusinessMappingSerializer, responses={201: envelope('BusinessMappingCreatedResponse', BusinessMappingResultSerializer())}))
class BusinessMappingView(DataModuleView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        resource = request.query_params.get('resource', '')
        business.require(request.user, resource)
        rows = ImportMapping.objects.filter(creator=request.user, resource=resource)[:20]
        return response([{'id': str(row.pk), 'name': row.name, 'options': row.options} for row in rows])

    @transaction.atomic
    def post(self, request):
        serializer = BusinessMappingSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        values = serializer.validated_data; actor = authorize(request, 'data_io:import')
        options = business.options_for(actor, values['resource'], values['options'])
        if ImportMapping.objects.filter(creator=actor, resource=values['resource']).count() >= 20:
            raise ValidationError('每种资源最多保存20个个人映射模板')
        row = ImportMapping.objects.create(creator=actor, resource=values['resource'], name=values['name'], options=options)
        return response({'id': str(row.pk), 'name': row.name, 'options': row.options}, 201)

@extend_schema_view(delete=extend_schema(request=None, responses=MessageResponse))
class BusinessMappingDeleteView(DataModuleView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, mapping_id):
        actor = authorize(request, 'data_io:import')
        row = ImportMapping.objects.filter(pk=mapping_id, creator=actor).first()
        if row is None:
            raise NotFound()
        business.require(actor, row.resource)
        row.delete()
        return response(None)


def csv_response(headers, rows, name):
    buffer = io.StringIO(); buffer.write('\ufeff')
    writer = csv.writer(buffer); writer.writerow(headers)
    for row in rows:
        writer.writerow([spreadsheet_text(value) for value in row])
        if buffer.tell() > business.MAX_BYTES:
            raise ValidationError('下载超过10 MiB，请缩小范围')
    raw = buffer.getvalue().encode('utf-8')
    if len(raw) > business.MAX_BYTES:
        raise ValidationError('下载超过10 MiB，请缩小范围')
    result = HttpResponse(raw, content_type='text/csv; charset=utf-8')
    result['Content-Disposition'] = 'attachment; filename="' + name + '.csv"'
    result['X-Content-Type-Options'] = 'nosniff'
    return result


def error_rows_response(request, resource, source, sha256, options, failed, identifier):
    from apps.files.access import file_queryset_for_actor
    business.require(request.user, resource, options['mode'])
    if source is None or source.is_deleted or not file_queryset_for_actor(FileModel.objects.filter(pk=source.pk), request.user).exists():
        raise NotFound()
    with source.file.open('rb') as stream:
        raw = stream.read(business.MAX_BYTES + 1)
    if len(raw) > business.MAX_BYTES or business.hashlib.sha256(raw).hexdigest() != sha256:
        raise ValidationError('源文件发生变化')
    _, rows = business.parse_rows(raw, source.original_name)
    readable = business.fields_for(request.user, resource, 'read')
    schema, _, _ = business.resource_schema(resource)
    inverse = {target: column for column, target in options['mapping'].items()}
    names = [field['name'] for field in schema['fields']]
    for group in schema['details']:
        if group['name'] in readable:
            names.extend(group['name'] + '.' + field['name'] for field in group['fields'])
    columns = [(inverse[name], name) for name in names if name in readable and name in inverse]
    planned_rows = {item['row']: item.get('source_rows', [item['row']]) for item in options['rows']}
    result = csv_response(['source_row', 'error_code', *[target for _, target in columns]],
        ([number, error, *[rows[number - 2][column] for column, _ in columns]]
         for anchor, error in failed for number in planned_rows.get(anchor, [anchor])),
        'import-errors-' + str(identifier))
    _log(request, 'export', '下载业务导入错误行', str(identifier))
    return result


@extend_schema_view(get=extend_schema(responses={(200, 'text/csv'): OpenApiTypes.BINARY}))
class BusinessPreviewErrorsView(DataModuleView):
    permission_classes = [IsAuthenticated]

    def get(self, request, plan_id):
        plan = BusinessImportPlan.objects.select_related('source').filter(pk=plan_id, creator=request.user).first()
        if plan is None or plan.expires_at <= timezone.now():
            raise NotFound()
        return error_rows_response(request, plan.resource, plan.source, plan.source_sha256, plan.options,
            ((item['row'], item['error']) for item in plan.options['rows'] if item['error']), plan.pk)


@extend_schema_view(get=extend_schema(responses={(200, 'text/csv'): OpenApiTypes.BINARY}))
class BusinessErrorsView(DataModuleView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        from apps.tasks.models import ImportExecution
        execution = ImportExecution.objects.select_related('batch__source').filter(pk=task_id, record__creator=request.user).first()
        if execution is None or execution.batch.options.get('version') != 2:
            raise NotFound()
        batch = execution.batch
        return error_rows_response(request, batch.resource, batch.source, batch.source_sha256, batch.options,
            batch.receipts.filter(outcome='failed').order_by('row').values_list('row', 'error'), batch.pk)


@extend_schema_view(get=extend_schema(parameters=[OpenApiParameter('resource', str), OpenApiParameter('export_format', str)],
    responses={(200, 'text/csv'): OpenApiTypes.BINARY,
               (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): OpenApiTypes.BINARY}))
class BusinessExportView(DataModuleView):
    permission_classes = [IsAuthenticated]

    @query_budget()
    def get(self, request):
        resource = request.query_params.get('resource', '')
        schema, _, service = business.require(request.user, resource, export=True)
        if schema['structure'] != 'single':
            raise ValidationError('主子表请使用后台整单导出')
        format_name = request.query_params.get('export_format', 'csv')
        if format_name not in ('csv', 'xlsx') or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise ValidationError('导出格式或重复参数无效')
        params = request.query_params.copy(); params.pop('resource', None); params.pop('export_format', None)
        if set(params) & {'page', 'page_size', 'format'}:
            raise ValidationError('导出不接受分页参数')
        view = import_module('apps.' + resource + '.views').RecordViewSet()
        view.action, view.request, view.format_kwarg = 'list', SimpleNamespace(user=request.user, query_params=params), None
        from apps.core.list_queries import validate_list_query
        validate_list_query(view.request, view)
        queryset = view.filter_queryset(service.visible(request.user))
        fields = [field['name'] for field in schema['fields'] if field['name'] in business.fields_for(request.user, resource, 'read')]
        if not fields:
            raise PermissionDenied('当前角色没有该资源的字段读取权限')
        rows, size = [], 0
        for index, values in enumerate(queryset.values_list(*fields).iterator(chunk_size=500)):
            if index >= business.MAX_ROWS:
                raise ValidationError('导出超过5000行，请缩小筛选范围')
            row = []
            for value in values:
                text = str('' if value is None else value.isoformat() if hasattr(value, 'isoformat') else value)
                if len(text) > 32767 or any(ord(char) < 32 and char not in '\t\r\n' for char in text):
                    raise ValidationError('导出包含无效单元格')
                size += len(text.encode('utf-8'))
                if size > business.MAX_BYTES:
                    raise ValidationError('导出超过10 MiB，请缩小筛选范围')
                row.append(text)
            rows.append(row)
        if format_name == 'csv':
            result = csv_response(fields, rows, resource + '-export')
        else:
            from openpyxl import Workbook
            book = Workbook(); sheet = book.active; sheet.title = 'export'; sheet.append(fields)
            for row in rows:
                sheet.append([spreadsheet_text(value) for value in row])
            buffer = io.BytesIO(); book.save(buffer)
            if buffer.tell() > business.MAX_BYTES:
                raise ValidationError('导出超过10 MiB，请缩小筛选范围')
            result = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            result['Content-Disposition'] = 'attachment; filename="' + resource + '-export.xlsx"'
            result['X-Content-Type-Options'] = 'nosniff'
        _log(request, 'export', '导出单表业务数据', resource)
        return result
