"""
数据导入导出视图
"""

import csv
import io
import os

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes, OpenApiParameter
from apps.core.schema import envelope
from apps.core.error_i18n import error_text
from apps.core.query_budget import query_budget
from apps.core.schema import MessageResponse
from apps.core.client_ip import request_ip

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.files.models import FileModel
from apps.logs.models import OperationLog
from apps.permissions.permissions import HasPermission, has_permission_code
from apps.tasks.models import TaskRecord
from apps.tasks.serializers import TaskRecordSerializer

from .resources import get_resource, IMPORT_EXPORT_RESOURCES, export_queryset, import_allowed
from apps.permissions.field_permissions import allowed_fields
from .serializers import DataImportSerializer, DataExportSerializer, DataResourceDirectorySerializer
from .tasks import dispatch_task, run_data_import

# 导入文件仅允许这两种格式（.xls 旧格式未引入 xlrd 依赖，不支持）
IMPORT_ALLOWED_EXTENSIONS = ['xlsx', 'csv']


def spreadsheet_text(value):
    """文本列禁止以公式/控制字符开头；CSV 和 XLSX 使用同一策略。"""
    value = str('' if value is None else value)
    if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) or value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def _log(request, action, description, resource_id=''):
    OperationLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        resource='data_io',
        resource_id=resource_id,
        description=description,
        ip_address=request_ip(request) or '0.0.0.0',
    )


class DataModuleView(APIView):
    """已加载的 URL 在模块运行时关闭后也不能保留数据入口。"""
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        from apps.core.modules import module_enabled
        from apps.core.exceptions import APIError
        if not module_enabled('data_io'):
            raise APIError('数据导入导出模块已关闭', status_code=404)


@extend_schema_view(
    post=extend_schema(request=DataImportSerializer, responses=envelope('ImportResponse', TaskRecordSerializer())),
)
class DataImportView(DataModuleView):
    """上传导入文件，创建导入任务"""
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'data_io:import'

    def post(self, request):
        serializer = DataImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data['file']
        resource_name = serializer.validated_data['resource']
        if not import_allowed(request.user, resource_name):
            return Response({'code': 403, 'message': '没有该资源的导入权限或数据范围受限', 'data': None}, status=403)

        ext = os.path.splitext(uploaded.name)[1].lower().lstrip('.')
        if ext not in IMPORT_ALLOWED_EXTENSIONS:
            return Response({
                'code': 400,
                'message': error_text('仅支持 {extensions} 格式', extensions=', '.join(IMPORT_ALLOWED_EXTENSIONS)),
                'data': None,
            }, status=status.HTTP_400_BAD_REQUEST)

        from django.db import transaction
        from apps.tasks.reliability import authorize
        from .execution import register
        file_record = None
        try:
            with transaction.atomic():
                actor = authorize(request, 'data_io:import')
                if not import_allowed(actor, resource_name):
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied('没有该资源的导入权限或数据范围受限')
                file_record = FileModel.objects.create(
                    original_name=os.path.basename(uploaded.name), file=uploaded, file_type=ext,
                    size=uploaded.size, content_type=getattr(uploaded, 'content_type', '') or '',
                    description=f'数据导入文件（{resource_name}）', uploader=actor, purpose='import')
                record = TaskRecord.objects.create(name=f"导入{get_resource(resource_name)['label']}数据",
                    task_type='import', related_resource=resource_name, creator=actor,
                    result={'file_id': str(file_record.pk)})
                register(record, file_record, request)
                from apps.logs.audit import snapshot, write_audit
                write_audit(request=request, resource='task', identifier=record.pk, action='create',
                            after=snapshot('task', record), record=record, description='提交导入批次')
        except Exception:
            if file_record is not None and file_record.file:
                file_record.file.delete(save=False)
            raise
        return Response({
            'code': 200,
            'message': '导入任务已提交，请稍后查看任务结果',
            'data': TaskRecordSerializer(record).data,
        })


@extend_schema_view(
    get=extend_schema(responses=envelope('ImportStatusResponse', TaskRecordSerializer())),
    post=extend_schema(operation_id='data_io_import_retry', request=None, responses={202: envelope('ImportRetryResponse', TaskRecordSerializer())}),
)
class DataImportTaskView(DataModuleView):
    """查看自己发起的导入任务结果"""
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'POST':
            self.required_permission = 'data_io:import'
            return [IsAuthenticated(), HasPermission()]
        return super().get_permissions()

    def get(self, request, task_id):
        record = TaskRecord.objects.filter(id=task_id, creator=request.user).first()
        if record is None:
            return Response({'code': 404, 'message': '任务不存在', 'data': None}, status=status.HTTP_404_NOT_FOUND)
        return Response({'code': 200, 'message': 'success', 'data': TaskRecordSerializer(record).data})

    def post(self, request, task_id):
        """人工接续：不再从头执行已提交的行。"""
        from .execution import resume
        new_record = resume(request, task_id)
        return Response({'code': 202, 'message': '已登记接续未提交行',
                         'data': TaskRecordSerializer(new_record).data}, status=202)



@extend_schema_view(
    get=extend_schema(parameters=[OpenApiParameter('resource', str)], responses={(200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): OpenApiTypes.BINARY}),
)
class ImportTemplateView(DataModuleView):
    """下载导入模板（xlsx，含表头与示例行）"""
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'data_io:import'

    def get(self, request):
        from openpyxl import Workbook

        resource_name = request.query_params.get('resource', 'users')
        config = get_resource(resource_name)
        if config is None or not config['importable']:
            return Response({'code': 400, 'message': error_text('未注册的资源：{resource}', resource=resource_name), 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)
        if not import_allowed(request.user, resource_name):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('没有该资源的导入权限或数据范围受限')

        wb = Workbook()
        ws = wb.active
        ws.title = config['label']
        fields = config.get('import_fields', config['fields'])
        fields = [field for field in fields if field in allowed_fields(request.user, resource_name, 'write')]
        if not fields or any(field not in fields for field in config['required']):
            raise PermissionDenied('当前角色没有该资源的必需字段写入权限')
        ws.append(fields)
        example = {
            'users': ['zhangsan', 'zhangsan@example.com', '三', '张', '13800000000'],
            'roles': ['project_viewer', '导入后默认停用，授权需在角色管理单独配置'],
            'posts': ['project_assistant', '项目助理', '导入后默认停用，不分配人员'],
        }
        ws.append(example.get(resource_name, [''] * len(fields)))

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        response = HttpResponse(
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="import-template-{resource_name}.xlsx"'
        return response


@extend_schema_view(
    get=extend_schema(parameters=[OpenApiParameter('resource', str), OpenApiParameter('export_format', str, enum=['csv', 'xlsx'])], responses={(200, 'text/csv'): OpenApiTypes.BINARY, (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): OpenApiTypes.BINARY, 503: MessageResponse}),
)
class DataExportView(DataModuleView):
    """导出数据（csv / xlsx）"""
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'data_io:export'

    @query_budget()
    def get(self, request):
        from apps.core.modules import module_enabled
        from apps.core.exceptions import APIError
        serializer = DataExportSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data
        resource_name = filters['resource']
        export_format = filters['export_format']
        config = get_resource(resource_name)
        if not all(has_permission_code(request.user, code) for code in config['permissions']):
            raise APIError('没有该资源的导出权限', status_code=403)
        if resource_name == 'files' and not module_enabled('files'):
            raise APIError('文件模块已关闭', status_code=404)
        if config.get('module') and not module_enabled(config['module']):
            raise APIError('资源模块已关闭', status_code=404)
        fields = config['fields'][filters['log_type']] if resource_name == 'logs' else config['fields']
        fields = [field for field in fields if field in allowed_fields(request.user, resource_name, 'read')]
        if not fields:
            raise APIError('当前角色没有该资源的字段读取权限', status_code=403)
        queryset = export_queryset(resource_name, request.user, filters)
        # 只查询白名单，关联字段由 values_list 一次 JOIN，避免逐行额外查询。
        rows = []
        text_size = 0
        for index, values in enumerate(queryset.values_list(*fields).iterator(chunk_size=500)):
            if index >= EXPORT_MAX_ROWS:
                raise APIError('导出超过 5000 行，请缩小筛选范围；未生成部分文件', status_code=413)
            row = []
            for field, value in zip(fields, values):
                if resource_name == 'users':
                    from apps.core.sensitive import mask_email, mask_phone
                    if field == 'email':
                        value = mask_email(value)
                    elif field == 'phone':
                        value = mask_phone(value)
                value = spreadsheet_text(value.isoformat() if hasattr(value, 'isoformat') else value)
                if len(value) > 32767 or any(ord(character) < 32 and character not in '\t\r\n' for character in value):
                    raise APIError('导出包含超长或无效单元格，请调整数据后重试', status_code=400)
                text_size += len(value.encode('utf-8'))
                if text_size > EXPORT_MAX_BYTES:
                    raise APIError('导出超过 10 MiB，请缩小筛选范围；未生成部分文件', status_code=413)
                row.append(value)
            rows.append(row)
        if export_format == 'csv':
            buffer = io.StringIO()
            buffer.write('\ufeff')
            writer = csv.writer(buffer)
            writer.writerow(fields)
            writer.writerows(rows)
            content = buffer.getvalue().encode('utf-8')
            content_type = 'text/csv; charset=utf-8'
        else:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = config['label']
            ws.append(fields)
            for row in rows:
                ws.append(row)
            buffer = io.BytesIO()
            wb.save(buffer)
            content = buffer.getvalue()
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        if len(content) > EXPORT_MAX_BYTES:
            raise APIError('导出超过 10 MiB，请缩小筛选范围；未生成部分文件', status_code=413)
        # 生成完成后写审计；审计失败由异常处理返回失败，不发送未审计的文件。
        _log(request, 'export', f'Export {resource_name} ({export_format}, {len(rows)} rows)', filters.get('log_type', ''))
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{resource_name}-export.{export_format}"'
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


EXPORT_MAX_ROWS = 5000
EXPORT_MAX_BYTES = 10 * 1024 * 1024


@extend_schema_view(get=extend_schema(responses=envelope('DataResourceDirectoryResponse', DataResourceDirectorySerializer())))
class DataResourcesView(DataModuleView):
    """只展示当前用户可访问的能力，导出与导入资格独立。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.modules import module_enabled
        resources = []
        for key, config in IMPORT_EXPORT_RESOURCES.items():
            if key == 'files' and not module_enabled('files'):
                continue
            if config.get('module') and not module_enabled(config['module']):
                continue
            importable = import_allowed(request.user, key)
            exportable = config['exportable'] and has_permission_code(request.user, 'data_io:export') and all(has_permission_code(request.user, code) for code in config['permissions'])
            if importable or exportable:
                resources.append({'resource': key, 'label': config['label'], 'importable': importable, 'exportable': exportable})
        return Response({'code': 200, 'message': 'success', 'data': {'resources': resources, 'max_rows': EXPORT_MAX_ROWS, 'max_bytes': EXPORT_MAX_BYTES}})
