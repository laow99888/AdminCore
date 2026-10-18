"""
权限系统 URL 配置
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoleViewSet, PermissionViewSet, MenuViewSet
from .diagnostics import FieldDiagnosticView

router = DefaultRouter()
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'permissions', PermissionViewSet, basename='permission')
router.register(r'menus', MenuViewSet, basename='menu')

urlpatterns = [
    path('field-diagnostics/', FieldDiagnosticView.as_view(), name='field-diagnostics'),
    path('', include(router.urls)),
]
