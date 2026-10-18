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
        many=True, queryset=User.objects.filter(is_active=True, is_service_account=False), write_only=True,
    )
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(max_length=20000, required=False, allow_blank=True, default='')
    notification_type = serializers.ChoiceField(choices=Notification.TYPE_CHOICES, default='system')
    link = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    data = serializers.JSONField(required=False, allow_null=True, default=None)

    def to_internal_value(self, data):
        # PrimaryKeyRelatedField(many=True) 在 validate_* 前逐项查询，必须先限制输入长度。
        ids = data.get('recipient_ids') if hasattr(data, 'get') else None
        if not isinstance(ids, list) or not 1 <= len(ids) <= 1000:
            raise serializers.ValidationError({'recipient_ids': '收件人须为 1 到 1000 项的列表'})
        if len({str(identifier) for identifier in ids}) != len(ids):
            raise serializers.ValidationError({'recipient_ids': '收件人不能重复'})
        import json
        if len(json.dumps(data.get('data'), ensure_ascii=False)) > 20000:
            raise serializers.ValidationError({'data': '附加数据最大 20000 字符'})
        return super().to_internal_value(data)

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
