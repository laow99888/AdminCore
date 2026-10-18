"""只能读取和更新本人在当前租户的偏好；GET 不产生记录。"""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auth_app.write_authorization import authorize_write
from apps.core.schema import envelope
from apps.core.system_views import VersionConflict
from apps.logs.audit import write_audit
from .message_serializers import StrictMessageSerializer
from .models import NotificationPreference
from .preferences import CHANNELS, EVENTS, OPTIONAL_EVENTS, preference_for, preference_queryset


class PreferenceWriteSerializer(StrictMessageSerializer):
    revision = serializers.IntegerField(min_value=0)
    subscriptions = serializers.ListField(child=serializers.ChoiceField(choices=OPTIONAL_EVENTS), max_length=len(OPTIONAL_EVENTS))
    channels = serializers.ListField(child=serializers.ChoiceField(choices=CHANNELS), max_length=len(CHANNELS))
    quiet_enabled = serializers.BooleanField()
    quiet_start = serializers.TimeField(input_formats=['%H:%M'], format='%H:%M')
    quiet_end = serializers.TimeField(input_formats=['%H:%M'], format='%H:%M')
    timezone = serializers.CharField(max_length=64)
    business_delivery_mode = serializers.ChoiceField(choices=['immediate', 'digest'], required=False)
    digest_minutes = serializers.ChoiceField(choices=[60, 1440], required=False)

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError('请选择有效的 IANA 时区') from None
        return value

    def validate(self, data):
        if len(set(data['subscriptions'])) != len(data['subscriptions']) or len(set(data['channels'])) != len(data['channels']):
            raise serializers.ValidationError('订阅和渠道不能重复')
        if data['quiet_start'] == data['quiet_end']:
            raise serializers.ValidationError('免打扰起止时间不能相同')
        return data


class EventPreferenceSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    required = serializers.BooleanField()


class PreferenceReadSerializer(PreferenceWriteSerializer):
    events = EventPreferenceSerializer(many=True)
    available_channels = serializers.ListField(child=serializers.CharField())


def representation(row):
    from .message_channels import enabled
    values = PreferenceWriteSerializer(row).data if row else {
        'revision': 0, 'subscriptions': list(OPTIONAL_EVENTS), 'channels': list(CHANNELS),
        'quiet_enabled': False, 'quiet_start': '22:00', 'quiet_end': '08:00', 'timezone': 'Asia/Shanghai',
        'business_delivery_mode': 'immediate', 'digest_minutes': 60,
    }
    return {**values, 'events': [{'code': key, **value} for key, value in EVENTS.items()],
            'available_channels': [channel for channel in CHANNELS if enabled(channel)]}


class NotificationPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=envelope('NotificationPreferences', PreferenceReadSerializer()))
    def get(self, request):
        response = Response({'code': 200, 'message': 'success', 'data': representation(preference_for(request.user.pk))})
        response['Cache-Control'] = 'private, no-store'
        return response

    @extend_schema(request=PreferenceWriteSerializer, responses=envelope('UpdatedNotificationPreferences', PreferenceReadSerializer()))
    @transaction.atomic
    def put(self, request):
        data = PreferenceWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        actor = authorize_write(request)
        row = preference_queryset().select_for_update().filter(user=actor).first()
        before = representation(row)
        values = dict(data.validated_data)
        revision = values.pop('revision')
        if revision != (row.revision if row else 0):
            raise VersionConflict()
        if row:
            for key, value in values.items():
                setattr(row, key, value)
            row.revision += 1
            row.save(update_fields=[*values, 'revision', 'updated_at'])
        else:
            row = NotificationPreference.objects.create(user=actor, **values)
        after = representation(row)
        write_audit(request=request, actor=actor, resource='notification_preference', identifier=row.pk,
                    action='update', before={key: before[key] for key in values}, after={key: after[key] for key in values})
        response = Response({'code': 200, 'message': 'success', 'data': after})
        response['Cache-Control'] = 'private, no-store'
        return response
