from apps.core.strict_serializers import StrictSerializer
import unicodedata

from rest_framework import serializers



def normalized_name(value):
    value = unicodedata.normalize('NFC', value).strip()
    if not value or any(unicodedata.category(char).startswith('C') or char in '/\\' for char in value):
        raise serializers.ValidationError('名称不能为空或包含控制字符、路径分隔符')
    return value


class FolderWriteSerializer(StrictSerializer):
    name = serializers.CharField(max_length=80)
    parent = serializers.UUIDField(allow_null=True)

    def validate_name(self, value):
        return normalized_name(value)


class FolderUpdateSerializer(FolderWriteSerializer):
    version = serializers.IntegerField(min_value=1)


class FolderVersionSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=1)


class FolderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    parent = serializers.UUIDField(source='parent_id', allow_null=True)
    version = serializers.IntegerField()


class OrganizationSerializer(StrictSerializer):
    version = serializers.IntegerField(min_value=0)
    folder = serializers.UUIDField(allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=32), max_length=10)

    def validate_tags(self, value):
        value = [normalized_name(item) for item in value]
        if len(set(item.casefold() for item in value)) != len(value):
            raise serializers.ValidationError('标签不能重复')
        return value


class FileLibrarySerializer(serializers.Serializer):
    folders = FolderSerializer(many=True)
    tags = serializers.ListField(child=serializers.CharField())
    tags_truncated = serializers.BooleanField()
