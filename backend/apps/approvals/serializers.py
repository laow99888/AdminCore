"""
审批流程序列化器
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import ApprovalRequest

User = get_user_model()


class ApprovalRequestSerializer(serializers.ModelSerializer):
    """审批申请序列化（读取）"""
    applicant_name = serializers.CharField(source='applicant.username', read_only=True)
    assignee_name = serializers.CharField(source='assignee.username', read_only=True)
    decided_by_name = serializers.CharField(source='decided_by.username', read_only=True, default=None)

    class Meta:
        model = ApprovalRequest
        fields = [
            'id', 'title', 'request_type', 'content', 'applicant', 'applicant_name',
            'assignee', 'assignee_name', 'status', 'decided_by', 'decided_by_name',
            'decision_comment', 'decided_at', 'extra_data', 'created_at',
        ]
        read_only_fields = fields


class ApprovalCreateSerializer(serializers.Serializer):
    """发起审批申请"""
    title = serializers.CharField(max_length=200)
    request_type = serializers.ChoiceField(choices=ApprovalRequest.TYPE_CHOICES, default='other')
    content = serializers.CharField()
    assignee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), source='assignee', required=False,
    )
    assignee_username = serializers.CharField(write_only=True, required=False)
    extra_data = serializers.JSONField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        username = attrs.pop('assignee_username', None)
        if username and 'assignee' in attrs:
            raise serializers.ValidationError('审批人只能使用 ID 或准确用户名之一')
        if username:
            assignee = User.objects.filter(username=username, is_active=True).first()
            if assignee is None:
                raise serializers.ValidationError({'assignee_username': '审批人不存在或已禁用'})
            attrs['assignee'] = assignee
        if 'assignee' not in attrs:
            raise serializers.ValidationError({'assignee_username': '请选择审批人'})
        from apps.core.personnel import candidates
        request = self.context.get('request')
        if request and not candidates(request.user).filter(pk=attrs['assignee'].pk).exists():
            raise serializers.ValidationError({'assignee_id': '审批人不在可选范围内，请重新选择'})
        return attrs


class ApprovalDecisionSerializer(serializers.Serializer):
    """审批决策"""
    comment = serializers.CharField(required=False, allow_blank=True, default='')
