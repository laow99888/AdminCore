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
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.files.models import FileModel
from apps.logs.models import OperationLog
from apps.permissions.permissions import HasPermission
from apps.tasks.models import TaskRecord
from apps.tasks.serializers import TaskRecordSerializer

from .resources import get_resource
from .serializers import DataImportSerializer
from .tasks import dispatch_task, run_data_import

# 导入文件仅允许这两种格式（.xls 旧格式未引入 xlrd 依赖，不支持）
IMPORT_ALLOWED_EXTENSIONS = ['xlsx', 'csv']


def spreadsheet_text(value):
    """文本列禁止以公式/控制字符开头；CSV 和 XLSX 使用同一策略。"""
    value = str(value or '')
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


@extend_schema_view(
    post=extend_schema(request=DataImportSerializer, responses=envelope('ImportResponse', TaskRecordSerializer())),
)
class DataImportView(APIView):
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
class DataImportTaskView(APIView):
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

        new_record = TaskRecord.objects.create(
            name=f'{record.name}（重试）',
            task_type='import',
            related_resource=record.related_resource,
            creator=request.user,
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
class ImportTemplateView(APIView):
    """下载导入模板（xlsx，含表头与示例行）"""
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'data_io:import'

    def get(self, request):
        from openpyxl import Workbook

        resource_name = request.query_params.get('resource', 'users')
        config = get_resource(resource_name)
        if config is None:
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
class DataExportView(APIView):
    """导出数据（csv / xlsx）"""
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'data_io:export'

    def get(self, request):
        resource_name = request.query_params.get('resource', 'users')
        # 注意：参数名不能用 format，会触发 DRF 内容协商的 404
        export_format = request.query_params.get('export_format', 'csv').lower()
        config = get_resource(resource_name)
        if config is None:
            return Response({'code': 400, 'message': f'未注册的资源：{resource_name}', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)
        if export_format not in ('csv', 'xlsx'):
            return Response({'code': 400, 'message': '仅支持 csv / xlsx 格式', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)

        fields = config['fields']
        queryset = config['export_queryset']()
        from apps.core.data_scope import scope_queryset
        queryset = scope_queryset(queryset, request.user, 'user', 'pk')
        count = queryset.count()
        _log(request, 'export', f'Export {resource_name} ({export_format}, {count} rows)')

        if export_format == 'csv':
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{resource_name}-export.csv"'
            # 加 BOM 保证 Excel 打开中文不乱码
            response.write('\ufeff')
            writer = csv.writer(response)
            writer.writerow(fields)
            for obj in queryset.iterator():
                writer.writerow([spreadsheet_text(getattr(obj, field, '')) for field in fields])
            return response

        # xlsx
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = config['label']
        ws.append(fields)
        for obj in queryset.iterator():
            ws.append([spreadsheet_text(getattr(obj, field, '')) for field in fields])
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        response = HttpResponse(
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{resource_name}-export.xlsx"'
        return response
