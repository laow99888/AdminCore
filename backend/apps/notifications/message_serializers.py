from rest_framework import serializers
from collections.abc import Mapping
from drf_spectacular.utils import extend_schema_field
from apps.core.personnel import PeoplePaginationSerializer

from .models import MessageTemplate, MessageTemplateVersion, MessageDelivery


class TemplateVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageTemplateVersion
        fields = ['id', 'number', 'subject', 'body', 'variables', 'created_at']
        read_only_fields = fields


class MessageTemplateSerializer(serializers.ModelSerializer):
    current = serializers.SerializerMethodField()

    @staticmethod
    @extend_schema_field(TemplateVersionSerializer())
    def get_current(row) -> dict:
        current = row.current_versions[0] if hasattr(row, 'current_versions') else row.versions.get(number=row.revision)
        return TemplateVersionSerializer(current).data

    class Meta:
        model = MessageTemplate
        fields = ['id', 'code', 'name', 'enabled', 'revision', 'current', 'created_at', 'updated_at']
        read_only_fields = fields


class StrictMessageSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping) and set(data) - set(self.fields):
            raise serializers.ValidationError({'fields': '不允许的通知字段'})
        return super().to_internal_value(data)


class TemplateWriteSerializer(StrictMessageSerializer):
    code = serializers.RegexField(r'^[a-z][a-z0-9_-]{0,39}$', max_length=40)
    name = serializers.CharField(max_length=100)
    enabled = serializers.BooleanField(default=True)
    revision = serializers.IntegerField(min_value=0)
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(max_length=20000, allow_blank=True, trim_whitespace=False)
    variables = serializers.ListField(child=serializers.CharField(max_length=32), max_length=20)


class TemplatePreviewSerializer(StrictMessageSerializer):
    revision = serializers.IntegerField(min_value=1)
    values = serializers.DictField(child=serializers.CharField(max_length=2000, allow_blank=True, trim_whitespace=False))

    def validate_values(self, values):
        if len(values) > 20:
            raise serializers.ValidationError('变量最多 20 项')
        return values


class TemplateSendSerializer(TemplatePreviewSerializer):
    recipient_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)
    channels = serializers.ListField(child=serializers.ChoiceField(choices=MessageDelivery.CHANNELS), min_length=1, max_length=4)

    def validate(self, data):
        if len(set(data['recipient_ids'])) != len(data['recipient_ids']) or len(set(data['channels'])) != len(data['channels']):
            raise serializers.ValidationError('收件人和渠道不能重复')
        return data


class MessageDeliverySerializer(serializers.ModelSerializer):
    template_code = serializers.CharField(source='version.template.code', read_only=True)
    version_number = serializers.IntegerField(source='version.number', read_only=True)

    class Meta:
        model = MessageDelivery
        fields = ['id', 'template_code', 'version_number', 'recipient', 'creator', 'channel', 'request_id',
                  'status', 'attempts', 'last_error', 'expires_at', 'sent_at', 'created_at']
        read_only_fields = fields


class MessagePreviewResultSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body = serializers.CharField()


class ChannelsResultSerializer(serializers.Serializer):
    key = serializers.CharField()
    enabled = serializers.BooleanField()


class MessageVersionPageSerializer(serializers.Serializer):
    items = TemplateVersionSerializer(many=True)
    pagination = PeoplePaginationSerializer()


class SentDeliveriesSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    delivery_ids = serializers.ListField(child=serializers.UUIDField())
