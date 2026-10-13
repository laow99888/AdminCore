"""
文件管理后台配置
"""

from django.contrib import admin

from .models import FileModel


@admin.register(FileModel)
class FileModelAdmin(admin.ModelAdmin):
    exclude = ['purpose']
    list_display = ['original_name', 'file_type', 'size', 'uploader', 'download_count', 'is_deleted', 'created_at']
    list_filter = ['file_type', 'is_deleted', 'created_at']
    search_fields = ['original_name', 'description', 'uploader__username']
    readonly_fields = ['md5', 'download_count', 'created_at', 'updated_at']

    def get_queryset(self, request):
        # 托管头像只经本人专用链路管理，普通文件后台同样不能修改绑定。
        return super().get_queryset(request).filter(purpose='general')
