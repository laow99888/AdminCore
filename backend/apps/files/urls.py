"""
文件管理 URL 配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FileViewSet
from .document_views import FileVersionsView, FileCapacityView
from .library_views import FileLibraryView, FileFolderCreateView, FileFolderDetailView, FileOrganizationView
from .office_views import OfficeConfigView, OfficeSubmitView, OfficeJobView, OfficePdfView
from .resumable_views import (ResumableUploadStartView, ResumableUploadDetailView,
                               ResumableUploadChunkView, ResumableUploadCompleteView)

router = DefaultRouter()
router.register(r'', FileViewSet, basename='file')

urlpatterns = [
    path('capacity/', FileCapacityView.as_view(), name='file-capacity'),
    path('<uuid:file_id>/versions/', FileVersionsView.as_view(), name='file-versions'),
    path('library/', FileLibraryView.as_view(), name='file-library'),
    path('library/folders/', FileFolderCreateView.as_view(), name='file-folder-create'),
    path('library/folders/<uuid:folder_id>/', FileFolderDetailView.as_view(), name='file-folder-detail'),
    path('<uuid:file_id>/organization/', FileOrganizationView.as_view(), name='file-organization'),
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
