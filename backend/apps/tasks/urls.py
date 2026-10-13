"""
任务调度 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import TaskRecordViewSet
from .schedule_views import ScheduleView, ScheduleRunView

router = DefaultRouter()
router.register(r'', TaskRecordViewSet, basename='task-record')

urlpatterns = [
    path('schedules/', ScheduleView.as_view(http_method_names=['get', 'head', 'options'])),
    path('schedules/<slug:key>/', ScheduleView.as_view(http_method_names=['patch', 'options'])),
    path('schedules/<slug:key>/run/', ScheduleRunView.as_view()),
    path('', include(router.urls)),
]
