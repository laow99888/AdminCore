"""仅供租户 HTTP 契约夹具，避免临时开关污染首次导入的生产路由。"""
from django.urls import include, path

urlpatterns = [
    path('api/v1/tasks/', include('apps.tasks.urls')),
    path('api/v1/example/', include('apps.example.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/approvals/', include('apps.approvals.urls')),
    path('api/v1/online-forms/', include('apps.online_forms.urls')),
    path('api/v1/reports/', include('apps.reports.urls')),
    path('api/v1/files/', include('apps.files.urls')),
    path('api/v1/organization/', include('apps.core.organization_urls')),
    path('api/v1/feature-flags/', include('apps.feature_flags.urls')),
]
