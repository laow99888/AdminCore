"""
数据导入导出 URL 配置
"""

from django.urls import path

from .views import DataExportView, DataImportTaskView, DataImportView, ImportTemplateView, DataResourcesView
from .business_export_views import BusinessExportCreateView, BusinessExportStatusView, BusinessExportDownloadView
from .business_views import (BusinessCatalogView, BusinessInspectView, BusinessPreviewView, BusinessSubmitView,
                             BusinessMappingView, BusinessMappingDeleteView, BusinessErrorsView, BusinessPreviewErrorsView, BusinessExportView)

urlpatterns = [
    path('business/exports/', BusinessExportCreateView.as_view(), name='business-export-create'),
    path('business/exports/<uuid:task_id>/', BusinessExportStatusView.as_view(), name='business-export-status'),
    path('business/exports/<uuid:task_id>/download/', BusinessExportDownloadView.as_view(), name='business-export-download'),
    path('business/catalog/', BusinessCatalogView.as_view(), name='business-import-catalog'),
    path('business/inspect/', BusinessInspectView.as_view(), name='business-import-inspect'),
    path('business/preview/', BusinessPreviewView.as_view(), name='business-import-preview'),
    path('business/plans/<uuid:plan_id>/submit/', BusinessSubmitView.as_view(), name='business-import-submit'),
    path('business/plans/<uuid:plan_id>/errors/', BusinessPreviewErrorsView.as_view(), name='business-import-preview-errors'),
    path('business/mappings/', BusinessMappingView.as_view(), name='business-import-mappings'),
    path('business/mappings/<uuid:mapping_id>/', BusinessMappingDeleteView.as_view(), name='business-import-mapping'),
    path('business/import/<uuid:task_id>/errors/', BusinessErrorsView.as_view(), name='business-import-errors'),
    path('business/export/', BusinessExportView.as_view(), name='business-data-export'),
    path('resources/', DataResourcesView.as_view(), name='data-resources'),
    path('import/', DataImportView.as_view(), name='data-import'),
    path('import/<uuid:task_id>/', DataImportTaskView.as_view(), name='data-import-task'),
    path('template/', ImportTemplateView.as_view(), name='import-template'),
    path('export/', DataExportView.as_view(), name='data-export'),
]
