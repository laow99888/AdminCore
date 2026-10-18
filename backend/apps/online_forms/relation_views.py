from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import APIError
from apps.core.query_budget import query_budget
from apps.permissions.permissions import has_permission_code
from .attachment_views import AttachmentQuery
from .models import OnlineForm, OnlineFormRecord
from .relations import relation_queryset, relation_values, resources


class RelationItem(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()


class RelationQuery(AttachmentQuery):
    def to_internal_value(self, data):
        if set(data) - set(self.fields) or any(len(data.getlist(key)) != 1 for key in data):
            raise ValidationError({'parameters': '关联查询参数无效'})
        return super().to_internal_value(data)


class RelationChoices(serializers.Serializer):
    items = RelationItem(many=True)
    selected = RelationItem(allow_null=True)
    has_more = serializers.BooleanField()


class RelationResponse(serializers.Serializer):
    code = serializers.IntegerField()
    message = serializers.CharField()
    data = RelationChoices()


class RelationResource(serializers.Serializer):
    code = serializers.CharField()
    title = serializers.CharField()


class RelationResourcesResponse(serializers.Serializer):
    code = serializers.IntegerField()
    message = serializers.CharField()
    data = RelationResource(many=True)


def no_store(data):
    response = Response({'code': 200, 'message': 'success', 'data': data})
    response['Cache-Control'] = 'private, no-store'
    return response


class FormRelationResourcesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=RelationResourcesResponse)
    def get(self, request):
        if not (request.user.is_staff or request.user.is_superuser) or not has_permission_code(request.user, 'online_form:read'):
            raise PermissionDenied()
        return no_store([{'code': key, 'title': title} for key, title, _, _, _ in resources(request.user)])


def relation_at(definition, path):
    parts = path.split('.')
    if len(parts) == 3 and parts[1].isascii() and parts[1].isdecimal() and len(parts[1]) <= 3:
        parts.pop(1)
    fields = definition.get('fields', [])
    found = None
    for index, key in enumerate(parts):
        found = next((item for item in fields if item['key'] == key), None)
        if found is None or (index < len(parts) - 1 and found['type'] != 'detail'):
            return None
        fields = found.get('fields', [])
    return found if found and found['type'] == 'relation' else None


class FormRelationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[RelationQuery], responses=RelationResponse)
    def get(self, request, code):
        query = RelationQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        values, actor, record = query.validated_data, request.user, None
        if 'record_id' in values:
            if not has_permission_code(actor, 'online_form:record_read'):
                raise PermissionDenied()
            record = get_object_or_404(OnlineFormRecord.objects.select_related('form'), pk=values['record_id'], form__code=code, owner=actor)
            definition, tenant_id = record.definition_snapshot, record.tenant_id
            can_write = has_permission_code(actor, 'online_form:record_update') and record.approval_status not in {'pending', 'approved'}
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
        field = relation_at(definition, values['field'])
        if field is None:
            raise ValidationError({'field': '关联字段不存在'})
        if not values['resolve'] and not can_write:
            raise PermissionDenied()
        rows, label, query_kind = relation_queryset(field['resource'], actor, tenant_id)
        selected = values.get('selected')
        if record and not can_write and selected is not None:
            bound = {path: value for path, _, value in relation_values(definition, record.data)}
            if str(selected) != bound.get(values['field']):
                selected = None

        def public(row):
            return {'id': str(row.pk), 'title': str(getattr(row, label) or '')[:160]}
        with query_budget():
            current = rows.filter(pk=selected).first() if selected else None
            items, more = [], False
            if not values['resolve']:
                offset = (values['page'] - 1) * 30
                if values['q']:
                    rows = rows.filter(**{label + ('__icontains' if query_kind == 'contains' else ''): values['q']})
                found = list(rows.order_by('-created_at', 'pk')[offset:offset + 31])
                items, more = [public(row) for row in found[:30]], len(found) > 30
        return no_store({'items': items, 'selected': public(current) if current else None, 'has_more': more})
