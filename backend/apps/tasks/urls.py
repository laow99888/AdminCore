"""
任务调度 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import TaskRecordViewSet

router = DefaultRouter()
router.register(r'', TaskRecordViewSet, basename='task-record')

urlpatterns = [
    path('', include(router.urls)),
]
