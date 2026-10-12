"""
AdminCore 主 URL 配置
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from apps.core.views import DashboardStatsView

urlpatterns = [
    # 管理后台
    path('admin/', admin.site.urls),

    # API 路由
    path('api/v1/auth/', include('apps.auth_app.urls')),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/permissions/', include('apps.permissions.urls')),
    path('api/v1/files/', include('apps.files.urls')),
    path('api/v1/tasks/', include('apps.tasks.urls')),
    path('api/v1/logs/', include('apps.logs.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/data-io/', include('apps.data_io.urls')),
    path('api/v1/approvals/', include('apps.approvals.urls')),

    # API 文档
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # 仪表盘统计
    path('api/v1/dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),

    # 健康检查
    path('api/v1/health/', lambda request: JsonResponse({'status': 'ok'}), name='health-check'),
]

# 静态文件和媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
