"""
数据导入导出视图
"""

import csv
import io
import os

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiTypes, OpenApiParameter
from apps.core.schema import envelope

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

from .resources import get_resource, IMPORT_EXPORT_RESOURCES, export_queryset
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
        ip_address=request.META.get('REMOTE_ADDR', ''),
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
        from apps.core.data_scope import unrestricted_user_creation
        if not unrestricted_user_creation(request.user):
            return Response({'code': 403, 'message': '受限用户数据范围不能批量创建未分配部门的用户', 'data': None}, status=403)
        serializer = DataImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data['file']
        resource_name = serializer.validated_data['resource']

        ext = os.path.splitext(uploaded.name)[1].lower().lstrip('.')
        if ext not in IMPORT_ALLOWED_EXTENSIONS:
            return Response({
                'code': 400,
                'message': f'仅支持 {", ".join(IMPORT_ALLOWED_EXTENSIONS)} 格式',
                'data': None,
            }, status=status.HTTP_400_BAD_REQUEST)

        # 复用文件应用存储导入文件，便于任务重读和重试
        file_record = FileModel.objects.create(
            original_name=os.path.basename(uploaded.name),
            file=uploaded,
            file_type=ext,
            size=uploaded.size,
            content_type=getattr(uploaded, 'content_type', '') or '',
            description=f'数据导入文件（{resource_name}）',
            uploader=request.user,
            purpose='import',
        )

        record = TaskRecord.objects.create(
            name=f"导入{get_resource(resource_name)['label']}数据",
            task_type='import',
            related_resource=resource_name,
            creator=request.user,
            result={'file_id': str(file_record.id)},
        )
        dispatch_task(run_data_import, str(record.id))
        record.refresh_from_db()  # 同步执行模式下读取任务执行后的最终状态

        _log(request, 'import', f'Import {resource_name} data from {file_record.original_name}', str(record.id))
        return Response({
            'code': 200,
            'message': '导入任务已提交，请稍后查看任务结果',
            'data': TaskRecordSerializer(record).data,
        })


@extend_schema_view(
    get=extend_schema(responses=envelope('ImportStatusResponse', TaskRecordSerializer())),
    post=extend_schema(operation_id='data_io_import_retry', request=None, responses=envelope('ImportRetryResponse', TaskRecordSerializer())),
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
        """重试导入：复用原文件重新提交一个新任务"""
        record = TaskRecord.objects.filter(id=task_id, creator=request.user).first()
        if record is None:
            return Response({'code': 404, 'message': '任务不存在', 'data': None}, status=status.HTTP_404_NOT_FOUND)
        if not record.result or not record.result.get('file_id'):
            return Response({'code': 400, 'message': '原任务未关联导入文件，无法重试', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)

        config = get_resource(record.related_resource)
        if config is None or not config['importable'] or record.task_type != 'import':
            return Response({'code': 400, 'message': '该资源不支持导入重试', 'data': None}, status=400)

        from django.db import transaction
        from apps.core.data_scope import scope_queryset
        with transaction.atomic():
            source = scope_queryset(FileModel.objects.select_for_update().filter(is_deleted=False),
                                    request.user, 'file', 'uploader_id', fallback='self').filter(
                                        pk=record.result['file_id']).first()
            if not source:
                return Response({'code': 400, 'message': '导入源文件已过期或不可用，请重新上传', 'data': None}, status=400)
            new_record = TaskRecord.objects.create(
                name=f'{record.name}（重试）', task_type='import',
                related_resource=record.related_resource, creator=request.user,
                result={'file_id': record.result['file_id']},
            )
        dispatch_task(run_data_import, str(new_record.id))
        new_record.refresh_from_db()  # 同步执行模式下读取任务执行后的最终状态
        _log(request, 'import', f'Retry import task {record.id}', str(new_record.id))
        return Response({
            'code': 200,
            'message': '重试任务已提交',
            'data': TaskRecordSerializer(new_record).data,
        })


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
            return Response({'code': 400, 'message': f'未注册的资源：{resource_name}', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)

        wb = Workbook()
        ws = wb.active
        ws.title = config['label']
        ws.append(config['fields'])
        example = {
            'users': ['zhangsan', 'zhangsan@example.com', '三', '张', '13800000000'],
        }
        ws.append(example.get(resource_name, [''] * len(config['fields'])))

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
    get=extend_schema(parameters=[OpenApiParameter('resource', str), OpenApiParameter('export_format', str, enum=['csv', 'xlsx'])], responses={(200, 'text/csv'): OpenApiTypes.BINARY, (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): OpenApiTypes.BINARY}),
)
class DataExportView(DataModuleView):
    """导出数据（csv / xlsx）"""
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'data_io:export'

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
        fields = config['fields'][filters['log_type']] if resource_name == 'logs' else config['fields']
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
        from apps.core.data_scope import unrestricted_user_creation
        resources = []
        for key, config in IMPORT_EXPORT_RESOURCES.items():
            if key == 'files' and not module_enabled('files'):
                continue
            importable = config['importable'] and has_permission_code(request.user, 'data_io:import') and unrestricted_user_creation(request.user)
            exportable = config['exportable'] and has_permission_code(request.user, 'data_io:export') and all(has_permission_code(request.user, code) for code in config['permissions'])
            if importable or exportable:
                resources.append({'resource': key, 'label': config['label'], 'importable': importable, 'exportable': exportable})
        return Response({'code': 200, 'message': 'success', 'data': {'resources': resources, 'max_rows': EXPORT_MAX_ROWS, 'max_bytes': EXPORT_MAX_BYTES}})
