"""
AdminCore 主 URL 配置
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from apps.core.views import DashboardStatsView, health_check
from apps.core.views import ModuleCapabilitiesView
from apps.core.modules import MODULES, module_enabled
from apps.core.system_views import BrandView
from apps.core.api_lifecycle import api_versions

urlpatterns = [
    # 管理后台
    path('admin/', admin.site.urls),
    path('api/versions/', api_versions, name='api-versions'),

    # API 路由
    path('api/v1/auth/', include('apps.auth_app.urls')),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/permissions/', include('apps.permissions.urls')),
    path('api/v1/logs/', include('apps.logs.urls')),
    path('api/v1/reliability/', include('apps.core.event_urls')),
    path('api/v1/modules/', ModuleCapabilitiesView.as_view(), name='module-capabilities'),
    path('api/v1/brand/', BrandView.as_view(), name='brand'),

    # API 文档
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # 仪表盘统计
    path('api/v1/dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),

    # 健康检查
    path('api/v1/health/', health_check, name='health-check'),
]

# 静态文件和媒体文件服务
urlpatterns += [path(f'api/v1/{module.api_prefix}/', include(module.urls))
                for module in MODULES if module_enabled(module.key)]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
