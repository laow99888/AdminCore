"""
通知系统序列化器
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Notification

User = get_user_model()


class NotificationSerializer(serializers.ModelSerializer):
    """通知序列化"""
    sender_name = serializers.CharField(source='sender.username', read_only=True, default=None)

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'sender', 'sender_name', 'title', 'content',
            'notification_type', 'is_read', 'read_at', 'link', 'data', 'created_at',
        ]
        read_only_fields = fields


class NotificationCreateSerializer(serializers.Serializer):
    """发送通知（管理员）"""
    recipient_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.all(), write_only=True,
    )
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(required=False, allow_blank=True, default='')
    notification_type = serializers.ChoiceField(choices=Notification.TYPE_CHOICES, default='system')
    link = serializers.CharField(required=False, allow_blank=True, default='')
    data = serializers.JSONField(required=False, allow_null=True, default=None)

    def create(self, validated_data):
        recipients = validated_data.pop('recipient_ids')
        request = self.context['request']
        count = Notification.push(
            recipient_ids=[u.id for u in recipients],
            title=validated_data['title'],
            content=validated_data.get('content', ''),
            notification_type=validated_data.get('notification_type', 'system'),
            link=validated_data.get('link', ''),
            data=validated_data.get('data'),
            sender=request.user if request.user.is_authenticated else None,
        )
        return {'sent_count': count}
