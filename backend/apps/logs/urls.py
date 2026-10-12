"""
日志 URL 配置
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OperationLogViewSet, LoginLogViewSet, ExceptionLogViewSet

router = DefaultRouter()
router.register(r'operation', OperationLogViewSet, basename='operation-log')
router.register(r'login', LoginLogViewSet, basename='login-log')
router.register(r'exception', ExceptionLogViewSet, basename='exception-log')

urlpatterns = [
    path('', include(router.urls)),
]
