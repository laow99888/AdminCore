"""
核心视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.core.schema import envelope
from apps.core.schema import DashboardSerializer

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from .modules import module_enabled, capabilities
from .schema import ModuleCapabilitiesSerializer
from .data_scope import scope_queryset

User = get_user_model()


@never_cache
@require_safe
def liveness_check(request):
    """进程存活；不访问数据库、缓存或队列，不返回环境详情。"""
    return JsonResponse({'status': 'ok'})


@never_cache
@require_safe
def health_check(request):
    """就绪检查覆盖 DB/Redis；worker 由独立检查监控，避免启动循环。"""
    from django.db import connection, transaction
    from .diagnostics import redis_probe
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute("SET LOCAL statement_timeout = '500ms'")
            cursor.execute('SELECT 1')
            cursor.fetchone()
        if settings.CACHES['default']['BACKEND'] == 'django_redis.cache.RedisCache':
            if redis_probe('cache', settings.CACHES['default']['LOCATION'])['status'] != 'ok':
                return JsonResponse({'status': 'unavailable'}, status=503)
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})


class ModuleCapabilitiesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=envelope('ModuleCapabilitiesResponse', ModuleCapabilitiesSerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': capabilities()})


@extend_schema_view(
    get=extend_schema(responses=envelope('DashboardResponse', DashboardSerializer())),
)
class DashboardStatsView(APIView):
    """仪表盘统计：总量指标 + 7 日登录趋势 + 任务状态分布"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.approvals.models import ApprovalRequest
        from apps.files.models import FileModel
        from apps.logs.models import LoginLog, OperationLog
        from apps.tasks.models import TaskRecord

        user = request.user
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # 7 日登录趋势（含今天），date() 抽取在 sqlite/PostgreSQL 均可用
        start = today_start - timedelta(days=6)
        trend_rows = (
            scope_queryset(LoginLog.objects.filter(created_at__gte=start), user, 'log', 'user_id')
            .extra(select={'day': 'date(created_at)'})
            .values('day')
            .annotate(
                success=Count('id', filter=Q(status='success')),
                failed=Count('id', filter=~Q(status='success')),
            )
            .order_by('day')
        )
        trend_map = {str(r['day']): r for r in trend_rows}
        login_trend = [
            {
                'date': (start + timedelta(days=i)).date().isoformat(),
                'success': trend_map.get(str((start + timedelta(days=i)).date()), {}).get('success', 0),
                'failed': trend_map.get(str((start + timedelta(days=i)).date()), {}).get('failed', 0),
            }
            for i in range(7)
        ]

        task_status = {
            status: count
            for status, count in scope_queryset(TaskRecord.objects.all(), user, 'task', 'creator_id')
            .values_list('status').annotate(count=Count('id')).order_by()
        } if module_enabled('tasks') else {}

        return Response({
            'code': 200,
            'message': 'success',
            'data': {
                'totals': {
                    'users': scope_queryset(User.objects.filter(is_active=True), user, 'user', 'pk').count(),
                    'files': scope_queryset(FileModel.objects.filter(is_deleted=False, purpose='general'), user, 'file', 'uploader_id', fallback='self').count() if module_enabled('files') else 0,
                    'pending_approvals': ApprovalRequest.objects.filter(assignee=user, status='pending').count() if module_enabled('approvals') else 0,
                    'unread_notifications': user.notifications.filter(is_read=False).count() if module_enabled('notifications') else 0,
                    'today_logins': scope_queryset(LoginLog.objects.filter(created_at__gte=today_start, status='success'), user, 'log', 'user_id').count(),
                    'today_operations': scope_queryset(OperationLog.objects.filter(created_at__gte=today_start), user, 'log', 'user_id').count(),
                },
                'login_trend': login_trend,
                'task_status': task_status,
            },
        })
