"""
文件管理 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FileViewSet
from .office_views import OfficeConfigView, OfficeSubmitView, OfficeJobView, OfficePdfView

router = DefaultRouter()
router.register(r'', FileViewSet, basename='file')

urlpatterns = [
    path('office-preview/config/', OfficeConfigView.as_view(), name='office-preview-config'),
    path('office-preview/jobs/<uuid:job_id>/', OfficeJobView.as_view(), name='office-preview-job'),
    path('office-preview/jobs/<uuid:job_id>/pdf/', OfficePdfView.as_view(), name='office-preview-pdf'),
    path('<uuid:file_id>/office-preview/', OfficeSubmitView.as_view(), name='office-preview-submit'),
    path('', include(router.urls)),
]
