"""
任务调度 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import TaskRecordViewSet
from .schedule_views import ScheduleView, ScheduleRunView
from .backup_views import BackupStatusView, BackupPreflightView, BackupRestoreView, BackupRestoreRequestView

router = DefaultRouter()
router.register(r'', TaskRecordViewSet, basename='task-record')

urlpatterns = [
    path('backups/', BackupStatusView.as_view()),
    path('backups/<slug:timestamp>/preflight/', BackupPreflightView.as_view()),
    path('backups/<slug:timestamp>/restore/', BackupRestoreView.as_view()),
    path('backups/restore-requests/<uuid:request_id>/', BackupRestoreRequestView.as_view()),
    path('schedules/', ScheduleView.as_view(http_method_names=['get', 'head', 'options'])),
    path('schedules/<slug:key>/', ScheduleView.as_view(http_method_names=['patch', 'options'])),
    path('schedules/<slug:key>/run/', ScheduleRunView.as_view()),
    path('', include(router.urls)),
]
