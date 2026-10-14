from collections.abc import Mapping
from rest_framework import serializers
from .models import Announcement


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ['id', 'title', 'content', 'status', 'version', 'published_at', 'created_at', 'updated_at']
        read_only_fields = fields


class AnnouncementWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, trim_whitespace=True)
    content = serializers.CharField(max_length=20000, trim_whitespace=True)
    version = serializers.IntegerField(min_value=0)

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)
        extra = set(data) - set(self.fields)
        if extra:
            raise serializers.ValidationError({'fields': '不允许的公告字段'})
        return super().to_internal_value(data)


class AnnouncementTransitionSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)
        if set(data) != {'version'}:
            raise serializers.ValidationError({'fields': '发布与撤回只接受 version'})
        return super().to_internal_value(data)
