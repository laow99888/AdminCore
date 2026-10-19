"""显式生成模块与审批/报表的接缝；不接受客户端指定模型、查询或回调。"""
from importlib import import_module
import json

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied

from apps.core.exceptions import APIError
from apps.core.modules import module_enabled


def registered_module(key):
    from apps.core.modules import MODULES
    if key not in {item.key for item in MODULES} or not apps.is_installed('apps.' + key):
        raise NotFound()
    manifest = import_module('apps.' + key + '.manifest')
    if getattr(manifest, 'GENERATED_BY', '') != 'AdminCore.codegen.v2':
        raise NotFound()
    schema = import_module('apps.' + key + '.schema').SCHEMA
    model = apps.get_model(key, schema['model'])
    service = import_module('apps.' + key + '.services').service
    if schema['module'] != key or service.model is not model:
        raise NotFound()
    return schema, model, service


def sync_approval(application, request):
    schema, model, service = registered_module(application.business_module)
    if not schema.get('approval'):
        raise APIError('业务审批接入已变化，不能完成流转', status_code=409)
    row = model.objects.select_for_update().filter(pk=application.business_record_id).first()
    if (row is None or row.approval_request_id != application.pk or row.approval_status != 'pending'
            or row.tenant_id != application.tenant_id or application.status not in {'approved', 'rejected', 'cancelled'}):
        raise APIError('业务审批关联或状态已变化，请管理员检查', status_code=409)
    before = service.projection(row)
    row.approval_status = application.status
    row.version += 1
    row.save(update_fields=['approval_status', 'version', 'updated_at'])
    service.audit(request=request, actor=request.user, resource=service.module, identifier=row.pk,
                  action='update', before=before, after=service.projection(row))


def redact_approval_snapshot(application, actor, data, *, read_snapshot=None):
    """按查看者当前权限过滤冻结快照；字段改名/模块失效时采取关闭访问。"""
    from apps.permissions.field_permissions import business_allowed_fields
    from apps.permissions.permissions import has_permission_code
    try:
        schema, _, _ = registered_module(application.business_module)
    except NotFound:
        return {**data, 'title': '业务审批', 'extra_data': {}, 'business_snapshot': {}}
    if not schema.get('approval'):
        return {**data, 'title': schema['title'], 'extra_data': {}, 'business_snapshot': {}}
    allowed = read_snapshot.fields(application.business_module) if read_snapshot else business_allowed_fields(actor, application.business_module, 'read')
    can_read = read_snapshot.can(application.business_module + ':read') if read_snapshot else has_permission_code(actor, application.business_module + ':read')
    if not module_enabled(application.business_module) or not can_read:
        allowed = set()
    snapshot = data.get('business_snapshot') or {}
    title_field = next(field for field in schema['fields'] if field['name'] == schema['approval']['title_field'])
    title_key = title_field['label'] + ' (' + title_field['name'] + ')'
    # 可见标题由冻结快照按当前权限投影；存储及通知只使用不含业务字段的标题。
    data = {**data, 'title': (schema['title'] + '：' + str(snapshot.get('fields', {}).get(title_key, application.business_record_id)))[:200]
            if allowed is None or title_field['name'] in allowed else schema['title']}
    if allowed is None:
        return data
    fields = {field['label'] + ' (' + field['name'] + ')' for field in schema['fields'] if field['name'] in allowed}
    details = {}
    for group in schema['details']:
        label = group['label'] + ' (' + group['name'] + ')'
        if group['name'] in allowed and isinstance(snapshot.get('details', {}).get(label), list):
            names = {field['label'] + ' (' + field['name'] + ')' for field in group['fields'] if group['name'] + '.' + field['name'] in allowed}
            details[label] = [{key: value for key, value in row.items() if key in names} for row in snapshot['details'][label]]
    return {**data, 'title': data['title'] if schema['approval']['title_field'] in allowed else schema['title'],
            'extra_data': {key: value for key, value in (data.get('extra_data') or {}).items() if key in allowed},
            'business_snapshot': {'fields': {key: value for key, value in snapshot.get('fields', {}).items() if key in fields}, 'details': details}}


def business_action(service, request, identifier, version, operation):
    from apps.approvals.models import ApprovalFlow, ApprovalRequest, ApprovalAction, validate_flow_definition
    from apps.approvals.engine import enter_next, input_data
    from apps.core.events import enqueue_event
    schema = service.schema
    if not schema.get('approval') or not module_enabled(service.module) or not module_enabled('approvals'):
        raise NotFound()
    with transaction.atomic():
        actor = service.locked_actor(request, 'submit' if operation == 'submit' else 'withdraw')
        # 与审批中心一致：申请行在业务行之前加锁，防止撤回与最终审批互相等待。
        candidate = service.visible(actor).filter(pk=identifier).first()
        if candidate is None:
            raise NotFound()
        application = None
        if operation == 'withdraw' and candidate.approval_request_id:
            application = ApprovalRequest.objects.select_for_update().filter(pk=candidate.approval_request_id).first()
        row = service.visible(actor).select_for_update(of=('self',)).filter(pk=identifier).first()
        if row is None:
            raise NotFound()
        if row.version != version:
            from .runtime import VersionConflict
            raise VersionConflict()
        if row.creator_id != actor.pk:
            raise PermissionDenied('业务审批只能由记录创建人提交或撤回')
        if operation == 'withdraw':
            if (application is None or row.approval_request_id != application.pk
                    or row.approval_status != 'pending' or application.status != 'pending'
                    or application.applicant_id != actor.pk):
                raise APIError('当前业务记录没有可撤回的审批', status_code=409)
            application.status = 'cancelled'; application.decided_at = timezone.now()
            application.save(update_fields=['status', 'decided_at', 'updated_at'])
            application.steps.filter(status='pending').update(status='cancelled', updated_at=timezone.now())
            ApprovalAction.objects.create(request=application, actor=actor, action='cancel')
            sync_approval(application, request)
            row.refresh_from_db()
            return row
        if row.approval_status not in {'draft', 'rejected', 'cancelled'}:
            raise APIError('当前业务状态不能重复提交审批', status_code=409)
        flow = ApprovalFlow.objects.select_for_update().filter(code=schema['approval']['flow_code'], status='published').first()
        if flow is None:
            raise ValidationError('登记的业务流程未发布或已归档')
        from django.core.exceptions import ValidationError as ModelValidationError
        try:
            validate_flow_definition(flow.definition)
        except ModelValidationError as error:
            raise ValidationError(error.messages) from error
        if flow.definition.get('schema_version') != 2:
            raise ValidationError('业务接入需要V2流程和显式输入登记')
        field_types = {f['name']: ('text' if f['kind'] in {'string', 'enum', 'dictionary'} else f['kind']) for f in schema['fields']}
        if any(field_types.get(item['key']) != item['type'] for item in flow.definition['inputs']):
            raise ValidationError('业务字段与流程输入登记不一致')
        data = {item['key']: getattr(row, item['key']) for item in flow.definition['inputs']}
        data = json.loads(json.dumps(data, cls=DjangoJSONEncoder))
        data = input_data(flow.definition, data)
        def field_values(instance, fields):
            return {field['label'] + ' (' + field['name'] + ')': getattr(instance, field['name'] + ('_id' if field['kind'] in {'file', 'relation'} else '')) for field in fields}
        snapshot = {'fields': field_values(row, schema['fields']), 'details': {
            group['label'] + ' (' + group['name'] + ')': [field_values(child, group['fields']) for child in getattr(row, group['name']).order_by('position', 'pk')]
            for group in schema['details']}}
        encoded = json.dumps(snapshot, cls=DjangoJSONEncoder, ensure_ascii=False)
        if len(encoded.encode()) > 131072:
            raise ValidationError('业务审批快照不能超过128KiB')
        snapshot = json.loads(encoded)
        # 提交时重新授权并锁定全部附件（含明细），随后与快照同事务登记历史保护。
        # 读取/管理附件的 ACL 不因业务或审批引用自动扩大。
        from .runtime import reference_queryset
        file_ids = set()
        def collect_files(instance, fields):
            file_ids.update(getattr(instance, field['name'] + '_id') for field in fields
                            if field['kind'] == 'file' and getattr(instance, field['name'] + '_id') is not None)
        collect_files(row, schema['fields'])
        for group in schema['details']:
            for child in getattr(row, group['name']).all():
                collect_files(child, group['fields'])
        if file_ids:
            queryset, _ = reference_queryset({'kind': 'file'}, actor)
            available = list(queryset.select_for_update(of=('self',)).filter(pk__in=file_ids).order_by('pk'))
            if {item.pk for item in available} != file_ids or any(item.tenant_id != row.tenant_id for item in available):
                raise ValidationError('审批附件不可用或不在授权范围内')
        before = service.projection(row)
        application = ApprovalRequest.objects.create(
            # 审批列表搜索、通知及站外投递不应复制可被字段权限隐藏的业务值。
            title=(schema['title'] + '：' + str(row.pk))[:200],
            request_type='other', content='业务审批：' + schema['title'], applicant=actor, assignee=actor,
            flow=flow, flow_version=flow.version, extra_data=data, tenant_id=row.tenant_id,
            business_module=service.module, business_record_id=row.pk, business_snapshot=snapshot)
        from apps.approvals.models import ApprovalFileReference
        ApprovalFileReference.objects.bulk_create([
            ApprovalFileReference(request=application, file_id=identifier, tenant_id=row.tenant_id)
            for identifier in sorted(file_ids)
        ])
        users = enter_next(application, initial=True)
        row.approval_status = 'pending'; row.approval_request = application; row.version += 1
        row.save(update_fields=['approval_status', 'approval_request', 'version', 'updated_at'])
        service.audit(request=request, actor=actor, resource=service.module, identifier=row.pk,
                      action='update', before=before, after=service.projection(row))
        enqueue_event(topic='notification.created', event_key=f'approval:{application.pk}:submitted',
            payload={'recipient_ids': [str(user.pk) for user in users], 'title': '待审批：' + application.title,
                     'content': '', 'notification_type': 'approval', 'link': '/approvals',
                     'data': {'request_id': str(application.pk)}}, request=request)
        return row
