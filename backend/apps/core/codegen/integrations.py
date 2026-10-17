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
        before = service.projection(row)
        application = ApprovalRequest.objects.create(
            title=(schema['title'] + '：' + str(getattr(row, schema['approval']['title_field'])))[:200],
            request_type='other', content='业务审批：' + schema['title'], applicant=actor, assignee=actor,
            flow=flow, flow_version=flow.version, extra_data=data, tenant_id=row.tenant_id,
            business_module=service.module, business_record_id=row.pk, business_snapshot=snapshot)
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
