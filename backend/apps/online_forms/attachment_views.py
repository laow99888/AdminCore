"""附件选项始终绑定实际表单/本人记录，不接受客户端提供动态业务 schema。"""
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import APIError
from apps.permissions.permissions import has_permission_code
from .attachments import file_values, public_file, readable_files
from .models import OnlineForm, OnlineFormRecord


class AttachmentQuery(serializers.Serializer):
    form_id = serializers.UUIDField(required=False)
    record_id = serializers.UUIDField(required=False)
    field = serializers.CharField(max_length=128)
    selected = serializers.UUIDField(required=False)
    q = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    page = serializers.IntegerField(min_value=1, max_value=1000, default=1)
    resolve = serializers.BooleanField(default=False)

    def validate(self, values):
        if ('form_id' in values) == ('record_id' in values):
            raise ValidationError('必须指定表单或记录上下文')
        return values


class AttachmentItem(serializers.Serializer):
    id = serializers.UUIDField()
    original_name = serializers.CharField()
    file_type = serializers.CharField()
    size = serializers.IntegerField()


class AttachmentChoices(serializers.Serializer):
    items = AttachmentItem(many=True)
    has_more = serializers.BooleanField()
    selected = AttachmentItem(allow_null=True)


class AttachmentResponse(serializers.Serializer):
    code = serializers.IntegerField()
    message = serializers.CharField()
    data = AttachmentChoices()


def field_at(definition, path):
    # 运行时路径如 lines.0.proof；schema 仅允许一层明细，索引不进入定义。
    parts = path.split('.')
    if len(parts) == 3 and parts[1].isascii() and parts[1].isdecimal() and len(parts[1]) <= 3:
        parts.pop(1)
    fields = definition.get('fields', [])
    field = None
    for index, key in enumerate(parts):
        field = next((row for row in fields if row['key'] == key), None)
        if field is None or (index < len(parts) - 1 and field['type'] != 'detail'):
            return None
        fields = field.get('fields', [])
    return field if field and field['type'] == 'file' else None


class FormAttachmentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[AttachmentQuery], responses=AttachmentResponse)
    def get(self, request, code):
        query = AttachmentQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        actor, record = request.user, None
        if 'record_id' in values:
            if not has_permission_code(actor, 'online_form:record_read'):
                raise PermissionDenied()
            record = get_object_or_404(OnlineFormRecord.objects.select_related('form'),
                pk=values['record_id'], form__code=code, owner=actor)
            definition, tenant_id = record.definition_snapshot, record.tenant_id
            can_write = has_permission_code(actor, 'online_form:record_update')
        else:
            form = get_object_or_404(OnlineForm.objects.all(), pk=values['form_id'], code=code)
            definition, tenant_id = form.definition, form.tenant_id
            if form.status == 'draft':
                if not (actor.is_staff or actor.is_superuser) or not has_permission_code(actor, 'online_form:read'):
                    raise PermissionDenied()
                can_write = has_permission_code(actor, 'online_form:update')
            else:
                if form.status != 'published':
                    raise APIError('表单已发布新版，请刷新后重新填写', status_code=409)
                if not has_permission_code(actor, 'online_form:record_create'):
                    raise PermissionDenied()
                can_write = True
        if field_at(definition, values['field']) is None:
            raise ValidationError({'field': '附件字段不存在'})
        if not values['resolve'] and not can_write:
            raise PermissionDenied()
        queryset = readable_files(actor, tenant_id)
        selected = values.get('selected')
        if record and not can_write and selected is not None:
            # 只读历史查看只解析当前字段内已绑定的值，不能借记录读取权限搜索文件。
            paths = dict(file_values(definition, record.data))
            if str(selected) != paths.get(values['field']):
                selected = None
        selected_row = queryset.filter(pk=selected).first() if selected is not None else None
        items, more = [], False
        if not values['resolve']:
            offset = (values['page'] - 1) * 30
            rows = list(queryset.filter(Q(original_name__icontains=values['q'])).order_by('-created_at', 'pk')[offset:offset + 31])
            items, more = [public_file(row) for row in rows[:30]], len(rows) > 30
        response = Response({'code': 200, 'message': 'success', 'data': {
            'items': items, 'has_more': more, 'selected': public_file(selected_row) if selected_row else None,
        }})
        response['Cache-Control'] = 'private, no-store'
        return response
