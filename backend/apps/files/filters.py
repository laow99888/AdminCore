import django_filters
from django.db.models import Exists, OuterRef

from .library import filter_folder, personal_rows
from .models import FileModel, FileOrganization


class FileFilter(django_filters.FilterSet):
    folder = django_filters.CharFilter(method='by_folder', label='个人目录UUID，或unfiled表示未分类；只匹配当前目录')
    tag = django_filters.CharFilter(method='by_tag', max_length=32, label='个人标签，精确匹配')

    class Meta:
        model = FileModel
        fields = ['file_type', 'uploader']

    def by_folder(self, queryset, name, value):
        return filter_folder(queryset, self.request.user, value)

    def by_tag(self, queryset, name, value):
        return queryset.filter(Exists(personal_rows(FileOrganization, self.request.user).filter(
            file_id=OuterRef('pk'), tags__name=value)))
