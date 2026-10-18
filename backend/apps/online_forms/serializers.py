from rest_framework import serializers
from .models import OnlineForm, OnlineFormRecord
from .validators import validate_definition


class OnlineFormSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    published_by_name = serializers.CharField(source='published_by.username', read_only=True, default=None)
    class Meta:
        model = OnlineForm
        fields = ['id', 'name', 'code', 'status', 'version', 'release_number', 'definition', 'approval_flow_code', 'approval_flow', 'approval_flow_version', 'created_by', 'created_by_name', 'published_by', 'published_by_name', 'published_at', 'created_at', 'updated_at']
        read_only_fields = fields


class OnlineFormDesignSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(required=False, min_value=1)
    class Meta:
        model = OnlineForm
        fields = ['id', 'name', 'code', 'status', 'version', 'release_number', 'definition', 'approval_flow_code']
        read_only_fields = ['id', 'status', 'release_number']
        validators = []
    def validate_definition(self, value):
        return validate_definition(value)
    def validate_code(self, value):
        if self.instance:
            if self.instance.code != value:
                raise serializers.ValidationError('已保存表单的编码不可修改')
            return value
        if OnlineForm.objects.filter(code=value).exists():
            raise serializers.ValidationError('表单编码已存在')
        if not isinstance(value, str) or not __import__('re').fullmatch(r'[a-z][a-z0-9-]{1,63}', value):
            raise serializers.ValidationError('表单编码必须为小写字母、数字和短横线')
        return value


class OnlineFormRecordSerializer(serializers.ModelSerializer):
    approval_enabled = serializers.SerializerMethodField()
    def get_approval_enabled(self, obj) -> bool:
        from apps.core.modules import module_enabled
        return bool(obj.form.approval_flow_id) and module_enabled('approvals')
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    form_name = serializers.CharField(source='form.name', read_only=True)
    release_number = serializers.IntegerField(source='form.release_number', read_only=True)
    form_status = serializers.CharField(source='form.status', read_only=True)
    class Meta:
        model = OnlineFormRecord
        fields = ['id', 'form', 'form_version', 'form_name', 'release_number', 'form_status', 'owner', 'owner_name', 'data', 'version', 'approval_status', 'approval_request', 'approval_enabled', 'created_at', 'updated_at']
        read_only_fields = fields


class OnlineFormRecordDetailSerializer(OnlineFormRecordSerializer):
    class Meta(OnlineFormRecordSerializer.Meta):
        fields = [*OnlineFormRecordSerializer.Meta.fields, 'definition_snapshot']
        read_only_fields = fields
