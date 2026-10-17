"""生成模块共用的授权、整单事务和查询协议；不执行用户提供的代码。"""
import hashlib
import json
from copy import copy
from importlib import import_module
from uuid import UUID

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, ValidationError, APIException
from rest_framework.response import Response

from apps.auth_app.sessions import locked_request_session
from apps.core.data_scope import scope_queryset
from apps.core.modules import MODULES, module_enabled
from apps.core.query_budget import query_budget
from apps.core.tenancy import current_tenant_id, enabled
from apps.permissions.permissions import has_permission_code


def prepare_labels(serializer, rows):
    """每组关联批量解析标签；权限撤销后只返回空标签，不泄漏关联名称。"""
    request = serializer.context.get('request')
    if request is None:
        return
    cache = serializer.context.setdefault('generated_labels', {})
    for field in serializer.field_spec:
        if field['kind'] not in {'relation', 'file', 'dictionary'}:
            continue
        key = json.dumps(field, sort_keys=True)
        entry = cache.setdefault(key, {})
        if field['kind'] == 'dictionary':
            loaded = serializer.context.setdefault('generated_dictionary_labels', set())
            if key not in loaded:
                loaded.add(key)
                try:
                    entry.update({item['value']: item['label'] for item in dictionary_options(field)})
                except ValidationError:
                    pass
        else:
            identifiers = {str(getattr(row, field['name'] + '_id')) for row in rows if getattr(row, field['name'] + '_id') is not None}
            missing = identifiers - entry.keys()
            if not missing:
                continue
            entry.update({identifier: '' for identifier in missing})
            try:
                queryset, label = reference_queryset(field, request.user)
                entry.update({str(item['pk']): str(item[label]) for item in queryset.filter(pk__in=missing).values('pk', label)})
            except (PermissionDenied, ValidationError):
                pass


class GeneratedListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        rows = list(data.all() if hasattr(data, 'all') else data)
        prepare_labels(self.child, rows)
        return super().to_representation(rows)


class VersionConflict(APIException):
    status_code = 409
    default_detail = '记录已变化或关联约束冲突，请刷新后重试'


class GeneratedSerializerMixin:
    def to_representation(self, instance):
        prepare_labels(self, [instance])
        return super().to_representation(instance)

    def get_display_labels(self, instance) -> dict[str, str]:
        cache = self.context.get('generated_labels', {})
        result = {}
        for field in self.field_spec:
            if field['kind'] in {'relation', 'file', 'dictionary'}:
                key = field['name'] + ('_id' if field['kind'] in {'relation', 'file'} else '')
                value = getattr(instance, key)
                result[field['name']] = cache.get(json.dumps(field, sort_keys=True), {}).get(str(value), '')
        return result

    def to_internal_value(self, data):
        allowed = {field['name'] for field in self.field_spec if field['form']}
        allowed.update(item['name'] for item in self.detail_spec)
        if not self.is_detail:
            allowed.add('version')
            if 'parent' in self.fields:
                allowed.add('parent')
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValidationError({'non_field_errors': ['只能提交可编辑的登记字段']})
        for field in self.field_spec:
            raw = data.get(field['name'])
            if field['kind'] == 'decimal' and raw is not None and not isinstance(raw, str):
                raise ValidationError({field['name']: '金额必须使用十进制字符串提交'})
        return super().to_internal_value(data)

    def validate(self, values):
        if not self.is_detail and 'version' not in values:
            raise ValidationError({'version': '必须提交读取到的版本'})
        return values


def reference_queryset(field, actor):
    if field['kind'] == 'file':
        from apps.files.models import FileModel
        from apps.files.access import file_queryset_for_actor
        if not module_enabled('files') or not has_permission_code(actor, 'file:read'):
            raise PermissionDenied('没有附件读取权限')
        return file_queryset_for_actor(FileModel.objects.filter(is_deleted=False, purpose='general'), actor), 'original_name'
    target = field['target']
    declaration = next((item for item in MODULES if item.key == target['module']), None)
    if declaration is None or not module_enabled(declaration.key):
        raise ValidationError('关联业务模块未登记或未启用')
    manifest = import_module('apps.' + declaration.key + '.manifest')
    if getattr(manifest, 'GENERATED_BY', '') not in {'AdminCore.codegen.v1', 'AdminCore.codegen.v2'}:
        raise ValidationError('关联目标必须为生成的业务模块')
    try:
        model = apps.get_model(declaration.key, target['model'])
    except LookupError as error:
        raise ValidationError('关联业务模型不可用') from error
    if model is None or not any(item.name == 'creator' for item in model._meta.fields):
        raise ValidationError('关联业务模型不可用')
    label = next((item for item in model._meta.fields if item.name == target['label'] and item.get_internal_type() in {'CharField', 'TextField'}), None)
    if label is None:
        raise ValidationError('关联显示字段必须为普通文本字段')
    if not has_permission_code(actor, declaration.key + ':read'):
        raise PermissionDenied('没有关联业务读取权限')
    return scope_queryset(model.objects.all(), actor, declaration.key, 'creator_id', fallback='self'), label.name


def dictionary_options(field, lock=False):
    from apps.core.models import DataDictionary
    queryset = DataDictionary.objects.filter(code=field['dictionary'], is_active=True)
    if lock:
        queryset = queryset.select_for_update()
    row = queryset.first()
    if row is None:
        raise ValidationError({field['name']: '字典不存在或未启用'})
    return [{'value': item['value'], 'label': item['label']} for item in row.items if item.get('is_active', True)]


class GeneratedService:
    def __init__(self, model, schema, extensions, audit):
        self.model, self.schema, self.extensions, self.audit = model, schema, extensions, audit
        self.module = schema['module']

    def visible(self, actor):
        return scope_queryset(self.model.objects.select_related('creator'),
                              actor, self.module, 'creator_id', fallback='self')

    def locked_actor(self, request, action):
        actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
        if actor is None:
            raise AuthenticationFailed('登录凭据已撤销')
        if request.auth is not None:
            locked_request_session(request, actor)
        if actor.must_change_password or not has_permission_code(actor, self.module + ':' + action):
            raise PermissionDenied('没有操作权限')
        return actor

    def validate_references(self, fields, values, actor, instance=None):
        for field in fields:
            key = field['name'] + ('_id' if field['kind'] in {'file', 'relation'} else '')
            value = values.get(key, getattr(instance, key, field['default']))
            if field['kind'] in {'file', 'relation'} and value is not None:
                queryset, _ = reference_queryset(field, actor)
                if not queryset.select_for_update(of=('self',)).filter(pk=value).exists():
                    raise ValidationError({field['name']: '关联记录不可用或不在授权范围内'})
            if field['kind'] == 'dictionary' and value:
                if value not in {item['value'] for item in dictionary_options(field, lock=True)}:
                    raise ValidationError({field['name']: '字典选项无效或已停用'})

    def validate_tree(self, row, parent_id, actor):
        if parent_id is None:
            return
        if not self.visible(actor).filter(pk=parent_id).exists():
            raise ValidationError({'parent': '父节点不可用或不在授权范围内'})
        seen = {str(row.pk)}
        current = parent_id
        for _ in range(1000):
            if current is None:
                return
            if str(current) in seen:
                raise ValidationError({'parent': '不能将节点移动到自身或其下级'})
            seen.add(str(current))
            parent = self.model.objects.filter(pk=current).values('parent_id').first()
            if parent is None:
                raise ValidationError({'parent': '父节点已变化'})
            current = parent['parent_id']
        raise ValidationError({'parent': '树层级超出1000层限制'})

    def projection(self, row):
        values = {field['name']: getattr(row, field['name'] + ('_id' if field['kind'] in {'file', 'relation'} else '')) for field in self.schema['fields']}
        if self.schema['structure'] == 'tree':
            values['parent'] = row.parent_id
        for detail in self.schema['details']:
            names = [item['name'] + ('_id' if item['kind'] in {'file', 'relation'} else '') for item in detail['fields']]
            values[detail['name']] = list(getattr(row, detail['name']).values(*names))
        if self.schema.get('approval'):
            values.update(approval_status=row.approval_status, approval_request_id=row.approval_request_id)
        digest = hashlib.sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return {'id': row.pk, 'creator_id': row.creator_id, 'version': row.version, 'record_sha256': digest}

    def mutate(self, request, action, values, identifier=None):
        try:
            with query_budget(), transaction.atomic():
                return self._mutate(request, action, dict(values), identifier)
        except (IntegrityError, ProtectedError) as error:
            raise VersionConflict() from error
        except ModelValidationError as error:
            raise ValidationError('业务字段、唯一编码或关联约束不满足要求') from error

    def _mutate(self, request, action, values, identifier):
        if not module_enabled(self.module):
            raise NotFound()
        actor = self.locked_actor(request, action)
        if self.schema['structure'] == 'tree':
            # 每个树模型共用一个锁，防止两个操作者同时移动产生环。
            from apps.core.models import BootstrapState
            key = 'codegen-tree:' + self.model._meta.label_lower
            BootstrapState.objects.get_or_create(key=key)
            BootstrapState.objects.select_for_update().get(key=key)
        row = None if action == 'create' else self.visible(actor).select_for_update(of=('self',)).filter(pk=identifier).first()
        if action != 'create' and row is None:
            raise NotFound()
        version = values.pop('version')
        if version != (0 if row is None else row.version):
            raise VersionConflict()
        before = self.projection(row) if row else None
        if row is not None and self.schema.get('approval'):
            if row.approval_status in {'pending', 'approved'} or action == 'delete' and row.approval_request_id:
                raise VersionConflict('审批中、已通过或已有审批历史的记录不允许此修改')
        if action == 'delete':
            self.extensions.before_delete(actor=actor, instance=row)
            self.audit(request=request, actor=actor, resource=self.module, identifier=row.pk, action=action, before=before, after=None)
            row.delete()
            return None
        details = {item['name']: values.pop(item['name']) for item in self.schema['details'] if item['name'] in values}
        self.extensions.before_save(actor=actor, instance=row, values=values, details=details)
        self.validate_references(self.schema['fields'], values, actor, row)
        if row is None:
            row = self.model(creator=actor, tenant_id=current_tenant_id() if enabled() else None)
        elif self.schema.get('approval'):
            row.approval_status = 'draft'
        if self.schema['structure'] == 'tree':
            self.validate_tree(row, values.get('parent_id', row.parent_id), actor)
        for name, value in values.items():
            setattr(row, name, value)
        row.version = 1 if action == 'create' else row.version + 1
        row.full_clean()
        row.save()
        if not self.visible(actor).filter(pk=row.pk).exists():
            raise PermissionDenied('记录不在当前数据范围内')
        for detail in self.schema['details']:
            if detail['name'] not in details:
                continue
            rows = details[detail['name']]
            if not detail['min_rows'] <= len(rows) <= detail['max_rows']:
                raise ValidationError({detail['name']: '明细行数超出限制'})
            relation = getattr(row, detail['name'])
            relation.all().delete()
            for position, data in enumerate(rows):
                self.validate_references(detail['fields'], data, actor)
                child = relation.model(parent=row, tenant_id=row.tenant_id, position=position, **data)
                child.full_clean()
                child.save()
        self.extensions.after_save(actor=actor, instance=row, action=action)
        # after_save 可能操作明细，清除旧预取缓存后计算实际写入摘要。
        row._prefetched_objects_cache = {}
        self.audit(request=request, actor=actor, resource=self.module, identifier=row.pk, action=action,
                   before=before, after=self.projection(row))
        return row


class GeneratedViewMixin:
    def _business_action(self, request, operation):
        from apps.core.idempotency import with_idempotency
        from .integrations import business_action
        if not isinstance(request.data, dict) or set(request.data) != {'version'}:
            raise ValidationError('业务动作只能提交版本号')
        version = serializers.IntegerField(min_value=1).run_validation(request.data['version'])
        with transaction.atomic():
            actor = self.generated_service.locked_actor(request, operation)
            self.get_object()
            def execute():
                row = business_action(self.generated_service, request, self.kwargs['pk'], version, operation)
                return Response({'code': 200, 'message': '操作成功', 'data': self.get_serializer(row).data})
            response = with_idempotency(request, f'{self.generated_schema["module"]}:{self.kwargs["pk"]}:{operation}', execute)
            if not self.generated_service.visible(actor).filter(pk=self.kwargs['pk']).exists():
                raise NotFound()
            return response

    @extend_schema(request=inline_serializer(name='GeneratedSubmitInput', fields={'version': serializers.IntegerField(min_value=1)}), responses=dict)
    @action(detail=True, methods=['post'])
    def submit(self, request, **kwargs):
        return self._business_action(request, 'submit')

    @extend_schema(request=inline_serializer(name='GeneratedWithdrawInput', fields={'version': serializers.IntegerField(min_value=1)}), responses=dict)
    @action(detail=True, methods=['post'])
    def withdraw(self, request, **kwargs):
        return self._business_action(request, 'withdraw')

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if getattr(self, 'action', '') != 'list':
            return queryset
        params = self.request.query_params
        for field in self.generated_schema['fields']:
            name, query = field['name'], field['query']
            for suffix, lookup in ([('_min', '__gte'), ('_max', '__lte')] if query == 'range' else [('', '__icontains' if query == 'contains' else '')] if query != 'none' else []):
                key = name + suffix
                if key in params:
                    # 使用真实 serializer 字段转换筛选值，拒绝未知枚举/非法日期/金额。
                    checker = copy(self.get_serializer().fields[name])
                    checker.read_only = False
                    value = checker.run_validation(params[key])
                    queryset = queryset.filter(**{name + lookup: value})
        if self.generated_schema['structure'] == 'tree' and 'parent' in params:
            parent = params['parent']
            if parent != 'root':
                try:
                    UUID(parent)
                except ValueError:
                    raise ValidationError({'parent': '父节点标识无效'}) from None
            queryset = queryset.filter(parent_id=None if parent == 'root' else parent)
        return queryset

    @property
    def list_query_choices(self):
        # 空 tuple 不代表枚举约束；列表 mixin 需通过 filterset_fields 登记参数名。
        return {}

    @property
    def filterset_fields(self):
        # 自行使用 serializer 校验，禁止 DjangoFilterBackend 重复过滤 range/contains 参数。
        return ()

    @property
    def generated_query_parameters(self):
        names = []
        for field in self.generated_schema['fields']:
            if field['query'] != 'none':
                for suffix in (['_min', '_max'] if field['query'] == 'range' else ['']):
                    names.append(field['name'] + suffix)
        if self.generated_schema['structure'] == 'tree':
            names.append('parent')
        return names

    @extend_schema(parameters=[], responses=inline_serializer(name='GeneratedChoiceResponse', fields={
        'code': serializers.IntegerField(), 'message': serializers.CharField(),
        'data': inline_serializer(name='GeneratedChoiceData', fields={
            'items': inline_serializer(name='GeneratedChoice', fields={'value': serializers.CharField(), 'label': serializers.CharField()}, many=True),
            'has_more': serializers.BooleanField()})}))
    @action(detail=False, methods=['get'], url_path='choices')
    def choices(self, request):
        params = request.query_params
        if set(params) - {'field', 'q', 'page'} or any(len(params.getlist(key)) != 1 or len(params[key]) > 200 or '\x00' in params[key] for key in params):
            raise ValidationError('选项查询参数无效')
        key = params.get('field', '')
        fields = {item['name']: item for item in self.generated_schema['fields']}
        for detail in self.generated_schema['details']:
            fields.update({detail['name'] + '.' + item['name']: item for item in detail['fields']})
        if key == 'parent' and self.generated_schema['structure'] == 'tree':
            field = None
        else:
            field = fields.get(key)
            if field is None or field['kind'] not in {'relation', 'file', 'dictionary'}:
                raise ValidationError('字段没有远程选项')
        try:
            page = int(params.get('page', '1'))
            if not 1 <= page <= 10000:
                raise ValueError()
        except ValueError:
            raise ValidationError('选项页码无效') from None
        with query_budget():
            if field and field['kind'] == 'dictionary':
                options = dictionary_options(field)
                options = [item for item in options if params.get('q', '').lower() in item['label'].lower()]
            else:
                if field is None:
                    queryset = self.generated_service.visible(request.user)
                    label = next((item['name'] for item in self.generated_schema['fields'] if item['kind'] == 'string'), 'pk')
                else:
                    queryset, label = reference_queryset(field, request.user)
                if params.get('q'):
                    queryset = queryset.filter(**{label + '__icontains': params['q']})
                options = [{'value': str(row['pk']), 'label': str(row[label])} for row in queryset.order_by('pk').values('pk', label)[(page - 1) * 50:page * 50 + 1]]
                return Response({'code': 200, 'message': 'success', 'data': {'items': options[:50], 'has_more': len(options) > 50}})
        start = (page - 1) * 50
        return Response({'code': 200, 'message': 'success', 'data': {'items': options[start:start + 50], 'has_more': len(options) > start + 50}})
