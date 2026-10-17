"""
审批流程序列化器
"""

from django.contrib.auth import get_user_model
import json
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.core.serializer_fields import TenantPrimaryKeyRelatedField

from .models import ApprovalAction, ApprovalCC, ApprovalFlow, ApprovalRequest, ApprovalStep, validate_flow_definition

User = get_user_model()


class ApprovalRequestSerializer(serializers.ModelSerializer):
    """审批申请序列化（读取）"""
    applicant_name = serializers.CharField(source='applicant.username', read_only=True)
    assignee_name = serializers.CharField(source='assignee.username', read_only=True)
    decided_by_name = serializers.CharField(source='decided_by.username', read_only=True, default=None)
    flow_name = serializers.CharField(source='flow.name', read_only=True, default=None)
    steps = serializers.SerializerMethodField()
    cc_recipients = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = [
            'id', 'title', 'request_type', 'content', 'applicant', 'applicant_name',
            'assignee', 'assignee_name', 'status', 'decided_by', 'decided_by_name',
            'decision_comment', 'decided_at', 'extra_data', 'created_at', 'flow', 'flow_name',
            'flow_version', 'current_node', 'workflow_version', 'steps', 'cc_recipients',
            'business_module', 'business_record_id', 'business_snapshot',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_steps(self, obj):
        rows = getattr(obj, '_prefetched_objects_cache', {}).get('steps')
        return ApprovalStepSerializer(rows if rows is not None else obj.steps.select_related('assignee', 'delegated_to').all(), many=True).data

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_cc_recipients(self, obj):
        rows = getattr(obj, '_prefetched_objects_cache', {}).get('cc_recipients')
        return ApprovalCCSerializer(rows if rows is not None else obj.cc_recipients.select_related('user').all(), many=True).data


class ApprovalStepSerializer(serializers.ModelSerializer):
    assignee_name = serializers.CharField(source='assignee.username', read_only=True, default=None)
    delegated_to_name = serializers.CharField(source='delegated_to.username', read_only=True, default=None)

    class Meta:
        model = ApprovalStep
        fields = ['id', 'node_key', 'kind', 'mode', 'sequence', 'status', 'assignee', 'assignee_name',
                  'candidates', 'delegated_to', 'delegated_to_name', 'comment', 'acted_by', 'acted_at', 'version']
        read_only_fields = fields


class ApprovalCCSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ApprovalCC
        fields = ['id', 'user', 'user_name', 'created_by', 'created_at']
        read_only_fields = fields


class ApprovalFlowSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    published_by_name = serializers.CharField(source='published_by.username', read_only=True, default=None)

    class Meta:
        model = ApprovalFlow
        fields = ['id', 'name', 'code', 'status', 'version', 'definition', 'created_by', 'created_by_name',
                  'published_by', 'published_by_name', 'published_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'version', 'created_by', 'created_by_name', 'published_by',
                            'published_by_name', 'published_at', 'created_at', 'updated_at']


class ApprovalFlowDesignSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(required=False, min_value=1)
    class Meta:
        model = ApprovalFlow
        fields = ['name', 'code', 'definition', 'version']

    def validate_definition(self, value):
        try:
            return validate_flow_definition(value)
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_code(self, value):
        if self.instance and self.instance.code == value:
            return value
        if ApprovalFlow.objects.filter(code=value).exists():
            raise serializers.ValidationError('流程编码已存在')
        return value


class ApprovalWorkflowActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, default='', max_length=4000)
    target_user_id = serializers.UUIDField(required=False)
    user_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=100, allow_empty=False)
    step_id = serializers.UUIDField(required=False)
    expected_version = serializers.IntegerField(required=False, min_value=1)


class ApprovalCreateSerializer(serializers.Serializer):
    """发起审批申请"""
    title = serializers.CharField(max_length=200)
    request_type = serializers.ChoiceField(choices=ApprovalRequest.TYPE_CHOICES, default='other')
    content = serializers.CharField(max_length=20000)
    assignee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), source='assignee', required=False,
    )
    assignee_username = serializers.CharField(write_only=True, required=False)
    flow_id = TenantPrimaryKeyRelatedField(queryset=ApprovalFlow.objects.filter(status='published'), source='flow', required=False)
    extra_data = serializers.JSONField(required=False, allow_null=True, default=None)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) & {'business_module', 'business_record_id', 'business_snapshot'}:
            raise serializers.ValidationError('不能从审批接口指定业务关联或快照')
        return super().to_internal_value(data)

    def validate_extra_data(self, value):
        def depth(row, level=0):
            if level > 5:
                raise serializers.ValidationError('附加数据最多嵌套5层')
            if isinstance(row, dict):
                for child in row.values():
                    depth(child, level + 1)
            elif isinstance(row, list):
                for child in row:
                    depth(child, level + 1)
        depth(value)
        if len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > 16384:
            raise serializers.ValidationError('附加数据最多16KiB')
        return value

    def validate(self, attrs):
        username = attrs.pop('assignee_username', None)
        if username and 'assignee' in attrs:
            raise serializers.ValidationError('审批人只能使用 ID 或准确用户名之一')
        if username:
            assignee = User.objects.filter(username=username, is_active=True).first()
            if assignee is None:
                raise serializers.ValidationError({'assignee_username': '审批人不存在或已禁用'})
            attrs['assignee'] = assignee
        if 'flow' in attrs and 'assignee' in attrs:
            raise serializers.ValidationError('流程和单个审批人只能选择一种')
        if 'assignee' not in attrs and 'flow' not in attrs:
            raise serializers.ValidationError({'assignee_username': '请选择审批人'})
        from apps.core.personnel import candidates
        request = self.context.get('request')
        if request and 'assignee' in attrs and not candidates(request.user).filter(pk=attrs['assignee'].pk).exists():
            raise serializers.ValidationError({'assignee_id': '审批人不在可选范围内，请重新选择'})
        return attrs


class ApprovalDecisionSerializer(serializers.Serializer):
    """审批决策"""
    comment = serializers.CharField(required=False, allow_blank=True, default='', max_length=4000)
