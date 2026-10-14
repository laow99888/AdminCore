"""
数据导入导出 URL 配置
"""

from django.urls import path

from .views import DataExportView, DataImportTaskView, DataImportView, ImportTemplateView, DataResourcesView

urlpatterns = [
    path('resources/', DataResourcesView.as_view(), name='data-resources'),
    path('import/', DataImportView.as_view(), name='data-import'),
    path('import/<uuid:task_id>/', DataImportTaskView.as_view(), name='data-import-task'),
    path('template/', ImportTemplateView.as_view(), name='import-template'),
    path('export/', DataExportView.as_view(), name='data-export'),
]
