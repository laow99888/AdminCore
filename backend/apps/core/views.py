"""
核心视图
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()


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
            LoginLog.objects.filter(created_at__gte=start)
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
            for status, count in TaskRecord.objects
            .values_list('status').annotate(count=Count('id')).order_by()
        }

        return Response({
            'code': 200,
            'message': 'success',
            'data': {
                'totals': {
                    'users': User.objects.filter(is_active=True).count(),
                    'files': FileModel.objects.filter(is_deleted=False).count(),
                    'pending_approvals': ApprovalRequest.objects.filter(assignee=user, status='pending').count(),
                    'unread_notifications': user.notifications.filter(is_read=False).count(),
                    'today_logins': LoginLog.objects.filter(created_at__gte=today_start, status='success').count(),
                    'today_operations': OperationLog.objects.filter(created_at__gte=today_start).count(),
                },
                'login_trend': login_trend,
                'task_status': task_status,
            },
        })
