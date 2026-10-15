"""统一响应结构和自定义 JWT 的 OpenAPI 定义。"""
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.utils import extend_schema_serializer, inline_serializer
from rest_framework import serializers
from drf_spectacular.openapi import AutoSchema
from .query_budget import QueryBudgetListMixin


class SessionJWTScheme(SimpleJWTScheme):
    target_class = 'apps.auth_app.authentication.SessionJWTAuthentication'


def envelope(name, data=None):
    fields = {'code': serializers.IntegerField(), 'message': serializers.CharField()}
    fields['data'] = data if data is not None else serializers.JSONField(allow_null=True)
    serializer = inline_serializer(name=name, fields=fields)
    extend_schema_serializer(many=False)(serializer.__class__)
    return serializer


MessageResponse = envelope('MessageResponse')


class QueryBudgetSchema(AutoSchema):
    def has_list_query_contract(self):
        return self.method == 'GET' and getattr(self.view, 'action', None) == 'list' and isinstance(self.view, QueryBudgetListMixin)

    def get_response_serializers(self):
        response = super().get_response_serializers()
        if self.has_list_query_contract():
            responses = dict(response) if isinstance(response, dict) else {200: response}
            responses.setdefault(400, MessageResponse)
            responses.setdefault(503, MessageResponse)
            return responses
        return response

    def _get_filter_parameters(self):
        parameters = super()._get_filter_parameters()
        if not self.has_list_query_contract():
            return parameters
        from .list_queries import allowed_query_parameters, MAX_QUERY_VALUE_LENGTH
        allowed = allowed_query_parameters(self.view)
        parameters = [parameter for parameter in parameters if parameter['name'] in allowed]
        for parameter in parameters:
            if parameter.get('schema', {}).get('type') == 'string':
                parameter['schema']['maxLength'] = MAX_QUERY_VALUE_LENGTH
            if parameter['name'] == 'ordering':
                parameter['description'] = ('逗号分隔，最多5项，前缀-表示降序；不支持或重复字段返回400。允许：'
                    + ', '.join(self.view.ordering_fields) + '。同值记录追加主键排序。')
        for name, choices in self.view.list_query_choices.items():
            parameters.append({'name': name, 'in': 'query', 'required': False,
                'schema': {'type': 'string', 'enum': list(choices)},
                'description': '资源查询视角；无此参数时使用默认范围。'})
        return parameters


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    otp_code = serializers.CharField(write_only=True, required=False, max_length=32)
    captcha_id = serializers.UUIDField(write_only=True, required=False)
    captcha_code = serializers.CharField(write_only=True, required=False, max_length=5)


class ResetPasswordRequestSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    must_change_password = serializers.BooleanField(default=True)

    def validate_password(self, value):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try:
            validate_password(value, self.context.get('user'))
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value


class CleanupRequestSerializer(serializers.Serializer):
    days = serializers.IntegerField(default=30, min_value=1, max_value=3650)


class DashboardTotalsSerializer(serializers.Serializer):
    users = serializers.IntegerField()
    files = serializers.IntegerField()
    pending_approvals = serializers.IntegerField()
    unread_notifications = serializers.IntegerField()
    today_logins = serializers.IntegerField()
    today_operations = serializers.IntegerField()


class LoginTrendSerializer(serializers.Serializer):
    date = serializers.DateField()
    success = serializers.IntegerField()
    failed = serializers.IntegerField()


class DashboardSerializer(serializers.Serializer):
    totals = DashboardTotalsSerializer()
    login_trend = LoginTrendSerializer(many=True)
    task_status = serializers.DictField(child=serializers.IntegerField())


class ModuleDescriptorSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    enabled = serializers.BooleanField()
    dependencies = serializers.ListField(child=serializers.CharField())
    paths = serializers.ListField(child=serializers.CharField())
    page_permissions = serializers.DictField(child=serializers.CharField(), required=False)


class ScopeResourceSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()


class ModuleCapabilitiesSerializer(serializers.Serializer):
    contract_version = serializers.IntegerField()
    preset = serializers.CharField()
    modules = ModuleDescriptorSerializer(many=True)
    scope_resources = ScopeResourceSerializer(many=True, required=False)
