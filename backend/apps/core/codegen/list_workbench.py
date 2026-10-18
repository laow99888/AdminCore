"""生成业务列表的有界条件、服务端查询方案与显式 ID 批量删除。"""
from copy import copy
import hashlib
import json
from uuid import UUID

from django.core import signing
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.exceptions import APIError
from apps.core.idempotency import with_idempotency
from apps.core.models import BootstrapState, SavedListView
from apps.core.query_budget import query_budget
from apps.core.tenancy import current_tenant_id, enabled
from apps.permissions.field_permissions import business_allowed_fields
from apps.permissions.permissions import has_permission_code

MAX_ADVANCED_LENGTH = 4096
SALT = 'admincore.generated-bulk-delete.v1'


class SavedQueryWriteSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    version = serializers.IntegerField(min_value=1, required=False)
    name = serializers.CharField(max_length=80)
    shared = serializers.BooleanField()
    definition = serializers.JSONField()


class SavedQueryDeleteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)


class SelectedRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)


class BulkPreviewSerializer(serializers.Serializer):
    selection = SelectedRecordSerializer(many=True, min_length=1, max_length=100)


class BulkDeleteSerializer(serializers.Serializer):
    preview_token = serializers.CharField(max_length=32768)
    confirmation = serializers.ChoiceField(choices=['删除选中记录'])


def schema_digest(schema):
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def operators(field):
    return ['eq', 'ne', *(['contains'] if field['query'] == 'contains' else []),
            *(['gte', 'lte'] if field['query'] == 'range' else [])]


def advanced_condition(view, value):
    """禁止关系路径、嵌套表达式和任意 lookup；真实 serializer 负责类型校验。"""
    if not isinstance(value, dict) or set(value) != {'match', 'conditions'}:
        raise ValidationError('高级条件结构无效')
    if value['match'] not in ('all', 'any') or not isinstance(value['conditions'], list) or len(value['conditions']) > 10:
        raise ValidationError('高级条件最多10项，匹配方式为all或any')
    fields = {field['name']: field for field in view.generated_schema['fields'] if field['query'] != 'none'}
    permitted = business_allowed_fields(view.request.user, view.generated_schema['module'], 'read')
    result = Q()
    for item in value['conditions']:
        if (not isinstance(item, dict) or set(item) != {'field', 'op', 'value'}
                or not isinstance(item['field'], str) or item['field'] not in fields):
            raise ValidationError('高级条件字段未登记')
        field = fields[item['field']]
        if permitted is not None and item['field'] not in permitted:
            raise PermissionDenied('没有筛选或排序字段读取权限')
        if not isinstance(item['op'], str) or item['op'] not in operators(field):
            raise ValidationError('高级条件运算符不受支持')
        if (not isinstance(item['value'], (str, int, float, bool))
                or len(str(item['value'])) > 200 or '\x00' in str(item['value'])):
            raise ValidationError('高级条件值无效或超过200个字符')
        checker = copy(view.get_serializer().fields[item['field']])
        checker.read_only = False
        checked = checker.run_validation(item['value'])
        lookup = {'eq': '', 'ne': '', 'contains': '__icontains', 'gte': '__gte', 'lte': '__lte'}[item['op']]
        condition = Q(**{item['field'] + lookup: checked})
        if item['op'] == 'ne':
            condition = ~condition
        result = result & condition if value['match'] == 'all' else result | condition
    return result


def parse_advanced(view, raw):
    if not isinstance(raw, str) or len(raw) > MAX_ADVANCED_LENGTH:
        raise ValidationError('高级条件最多4096个字符')
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValidationError('高级条件不是有效JSON') from None
    return advanced_condition(view, value)


def definition_for(view, value):
    from django.http import QueryDict, HttpRequest
    from rest_framework.request import Request
    from apps.core.list_queries import validate_list_query
    if not isinstance(value, dict) or set(value) != {'filters', 'advanced', 'ordering'}:
        raise ValidationError('查询方案需包含filters、advanced和ordering')
    filters, ordering = value['filters'], value['ordering']
    allowed = set(view.generated_query_parameters) - {'advanced', 'parent'}
    if (not isinstance(filters, dict) or set(filters) - allowed
            or any(not isinstance(item, str) for item in filters.values()) or not isinstance(ordering, str)):
        raise ValidationError('查询方案包含不支持的参数')
    raw = json.dumps(value['advanced'], ensure_ascii=False, separators=(',', ':'))
    params = QueryDict('', mutable=True)
    params.update({**filters, 'advanced': raw, 'ordering': ordering})
    # 使用正式列表的整套参数、类型、字段策略校验，不执行资源查询。
    original_request, original_action = view.request, view.action
    http = HttpRequest()
    http.method, http.GET = 'GET', params
    fake = Request(http)
    fake.user = original_request.user
    try:
        view.request, view.action = fake, 'list'
        validate_list_query(fake, view)
        view.filter_queryset(view.generated_service.model.objects.none())
    finally:
        view.request, view.action = original_request, original_action
    return {'filters': dict(filters), 'advanced': value['advanced'], 'ordering': ordering}


def identity(view):
    return {'actor': str(view.request.user.pk), 'tenant': str(current_tenant_id()) if enabled() and current_tenant_id() else '',
            'module': view.generated_schema['module'], 'schema': schema_digest(view.generated_schema)}


def stored_views(view):
    return SavedListView.objects.filter(module=view.generated_schema['module'],
        tenant_id=current_tenant_id() if enabled() else None)


def project_view(row, actor):
    return {'id': str(row.pk), 'name': row.name, 'shared': row.shared, 'version': row.version,
            'definition': row.definition, 'editable': (actor.is_staff or actor.is_superuser) if row.shared else row.owner_id == actor.pk}


def audit_projection(row):
    return {key: getattr(row, key) for key in ('id', 'module', 'owner_id', 'shared', 'version')} | {
        'definition_sha256': hashlib.sha256(json.dumps(row.definition, sort_keys=True).encode()).hexdigest()}


def selection_values(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        raise ValidationError('批量操作需明确选择1至100条记录')
    result = []
    for item in value:
        if (not isinstance(item, dict) or set(item) != {'id', 'version'} or not isinstance(item['id'], str)
                or type(item['version']) is not int or item['version'] < 1):
            raise ValidationError('选择项需包含有效ID和版本号')
        try:
            identifier = str(UUID(item['id']))
        except ValueError:
            raise ValidationError('选择项ID无效') from None
        result.append({'id': identifier, 'version': item['version']})
    if len({item['id'] for item in result}) != len(result):
        raise ValidationError('选择项不能重复')
    return result


class ListWorkbenchMixin:
    def get_permissions(self):
        # 旧的V2生成文件也可接入，无需重生成手写业务页面；其余动作保持原映射。
        if self.action in {'query_views', 'bulk_preview', 'bulk_delete'}:
            self.permission_map = {**self.permission_map, self.action: self.generated_schema['module'] + ':read'}
        return super().get_permissions()

    @extend_schema(methods=['GET'], parameters=[], responses=dict)
    @extend_schema(methods=['POST'], parameters=[], request=SavedQueryWriteSerializer, responses=dict)
    @extend_schema(methods=['DELETE'], parameters=[], request=SavedQueryDeleteSerializer, responses=dict)
    @action(detail=False, methods=['get', 'post', 'delete'], url_path='query-views')
    def query_views(self, request):
        if request.query_params:
            raise ValidationError('查询方案接口不接受查询参数')
        digest = schema_digest(self.generated_schema)
        if request.method == 'GET':
            rows = stored_views(self).filter(Q(owner=request.user) | Q(shared=True)).order_by('shared', 'name', 'id')
            items, unavailable = [], 0
            with query_budget():
                for row in rows[:60]:
                    try:
                        if row.schema_digest != digest:
                            raise ValidationError()
                        definition_for(self, row.definition)
                    except (ValidationError, PermissionDenied):
                        unavailable += 1
                        projected = project_view(row, request.user)
                        if projected['editable']:
                            # 所有者仍能删除失效方案释放配额，不返回失效条件中的敏感值。
                            items.append({**projected, 'available': False,
                                'definition': {'filters': {}, 'advanced': {'match': 'all', 'conditions': []}, 'ordering': ''}})
                        continue
                    items.append({**project_view(row, request.user), 'available': True})
            return Response({'code': 200, 'message': 'success', 'data': {'items': items, 'unavailable': unavailable}})
        values = request.data
        if not isinstance(values, dict):
            raise ValidationError('查询方案内容无效')
        with transaction.atomic():
            from apps.logs.audit import write_audit
            actor = self.generated_service.locked_actor(request, 'read')
            row = None
            if 'id' in values:
                identifier = serializers.UUIDField().run_validation(values['id'])
                row = stored_views(self).select_for_update().filter(pk=identifier).first()
                if row is None or not project_view(row, actor)['editable']:
                    raise NotFound()
                if type(values.get('version')) is not int or row.version != values['version']:
                    raise APIError('查询方案已变化，请刷新后重试', status_code=409)
            before = audit_projection(row) if row else None
            if request.method == 'DELETE':
                if row is None or set(values) != {'id', 'version'}:
                    raise ValidationError('删除查询方案需提交ID和版本号')
                write_audit(resource='list_view', identifier=row.pk, action='delete', request=request, before=before)
                row.delete()
                return Response({'code': 200, 'message': '操作成功', 'data': None})
            if set(values) != ({'name', 'shared', 'definition'} | ({'id', 'version'} if row else set())):
                raise ValidationError('查询方案内容无效')
            name = serializers.CharField(max_length=80).run_validation(values['name'])
            if type(values['shared']) is not bool:
                raise ValidationError('共享标识必须是布尔值')
            if (values['shared'] or row and row.shared) and not (actor.is_staff or actor.is_superuser):
                raise PermissionDenied('只有管理员可以管理共享查询方案')
            # 共享池跨所有者串行限额；个人池由上面的用户行锁串行。
            BootstrapState.objects.get_or_create(key='list-views:' + self.generated_schema['module'])
            BootstrapState.objects.select_for_update().get(key='list-views:' + self.generated_schema['module'])
            pool = stored_views(self).filter(shared=True) if values['shared'] else stored_views(self).filter(owner=actor, shared=False)
            pool = pool.exclude(pk=row.pk) if row else pool
            if pool.count() >= 30:
                raise ValidationError('每个模块最多30个个人方案和30个共享方案')
            if pool.filter(name=name).exists():
                raise APIError('同一范围内的查询方案名称已存在', status_code=409)
            definition = definition_for(self, values['definition'])
            if row is None:
                row = SavedListView(owner=actor, module=self.generated_schema['module'])
            elif row.owner_id != actor.pk and not values['shared']:
                raise ValidationError('不能将他人的共享方案转为个人方案')
            else:
                row.version += 1
            row.name, row.shared, row.definition, row.schema_digest = name, values['shared'], definition, digest
            row.save()
            write_audit(resource='list_view', identifier=row.pk, action='update' if before else 'create',
                        request=request, before=before, after=audit_projection(row))
        return Response({'code': 200, 'message': '操作成功', 'data': project_view(row, actor)})

    @extend_schema(parameters=[], request=BulkPreviewSerializer, responses=dict)
    @action(detail=False, methods=['post'], url_path='bulk-preview')
    def bulk_preview(self, request):
        if request.query_params or not isinstance(request.data, dict) or set(request.data) != {'selection'}:
            raise ValidationError('批量预检只接受明确的selection')
        if not has_permission_code(request.user, self.generated_schema['module'] + ':delete'):
            raise PermissionDenied('没有操作权限')
        selection = selection_values(request.data['selection'])
        results, ready = [], []
        with query_budget():
            visible = {str(row.pk): row for row in self.generated_service.visible(request.user).filter(pk__in=[item['id'] for item in selection])}
            for item in selection:
                row = visible.get(item['id'])
                status = ('unavailable' if row is None else 'conflict' if row.version != item['version'] else
                    'blocked' if self.generated_schema.get('approval') and (row.approval_status in {'pending', 'approved'} or row.approval_request_id) else 'ready')
                results.append({'id': item['id'], 'status': status})
                if status == 'ready':
                    ready.append(item)
        token = signing.dumps({**identity(self), 'selection': ready}, salt=SALT, compress=True) if ready else ''
        return Response({'code': 200, 'message': 'success', 'data': {'items': results, 'ready': len(ready), 'preview_token': token, 'expires_in': 900}})

    @extend_schema(parameters=[], request=BulkDeleteSerializer, responses=dict)
    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        if (request.query_params or not isinstance(request.data, dict) or set(request.data) != {'preview_token', 'confirmation'}
                or request.data['confirmation'] != '删除选中记录' or not isinstance(request.data['preview_token'], str)
                or len(request.data['preview_token']) > 32768 or not request.headers.get('Idempotency-Key')):
            raise ValidationError('批量删除需有效预检、确认文字和幂等键')
        try:
            planned = signing.loads(request.data['preview_token'], salt=SALT, max_age=900)
        except signing.BadSignature:
            raise ValidationError('批量预检已过期或无效，请重新预检') from None
        if {key: planned.get(key) for key in identity(self)} != identity(self):
            raise ValidationError('批量预检不属于当前用户、租户或业务版本')
        selection = selection_values(planned.get('selection'))
        with transaction.atomic():
            actor = self.generated_service.locked_actor(request, 'delete')
            if not has_permission_code(actor, self.generated_schema['module'] + ':read'):
                raise PermissionDenied('没有操作权限')
            def execute():
                if self.generated_schema['structure'] == 'tree':
                    from apps.core.models import BootstrapState
                    key = 'codegen-tree:' + self.generated_service.model._meta.label_lower
                    BootstrapState.objects.get_or_create(key=key)
                    BootstrapState.objects.select_for_update().get(key=key)
                # Lock all currently visible parents in canonical order before processing client order.
                list(self.generated_service.visible(actor).filter(
                    pk__in=[item['id'] for item in selection],
                ).order_by('pk').select_for_update(of=('self',)).values_list('pk', flat=True))
                items = []
                for item in selection:
                    try:
                        # 原事务服务重新检查授权、数据范围、版本、审批锁、扩展和数据库约束。
                        self.generated_service.mutate(request, 'delete', {'version': item['version']}, item['id'])
                        status = 'deleted'
                    except APIException as error:
                        status = {400: 'blocked', 404: 'unavailable', 409: 'conflict', 403: 'forbidden', 503: 'timeout'}.get(error.status_code)
                        if status is None:
                            raise
                    items.append({'id': item['id'], 'status': status})
                return Response({'code': 200, 'message': '操作成功', 'data': {'items': items,
                    'deleted': sum(item['status'] == 'deleted' for item in items)}})
            return with_idempotency(request, self.generated_schema['module'] + ':bulk-delete', execute)
