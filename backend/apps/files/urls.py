"""
文件管理 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FileViewSet
from .office_views import OfficeConfigView, OfficeSubmitView, OfficeJobView, OfficePdfView
from .resumable_views import (ResumableUploadStartView, ResumableUploadDetailView,
                               ResumableUploadChunkView, ResumableUploadCompleteView)

router = DefaultRouter()
router.register(r'', FileViewSet, basename='file')

urlpatterns = [
    path('uploads/', ResumableUploadStartView.as_view(), name='resumable-upload-start'),
    path('uploads/<uuid:upload_id>/', ResumableUploadDetailView.as_view(), name='resumable-upload-detail'),
    path('uploads/<uuid:upload_id>/chunks/<int:index>/', ResumableUploadChunkView.as_view(), name='resumable-upload-chunk'),
    path('uploads/<uuid:upload_id>/complete/', ResumableUploadCompleteView.as_view(), name='resumable-upload-complete'),
    path('office-preview/config/', OfficeConfigView.as_view(), name='office-preview-config'),
    path('office-preview/jobs/<uuid:job_id>/', OfficeJobView.as_view(), name='office-preview-job'),
    path('office-preview/jobs/<uuid:job_id>/pdf/', OfficePdfView.as_view(), name='office-preview-pdf'),
    path('<uuid:file_id>/office-preview/', OfficeSubmitView.as_view(), name='office-preview-submit'),
    path('', include(router.urls)),
]
