"""在线表单审批的受信服务；流程、租户、快照和附件均由服务器确定。"""
from copy import deepcopy
import json

from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.approvals.engine import enter_next, input_data
from apps.approvals.models import ApprovalAction, ApprovalFileReference, ApprovalFlow, ApprovalRequest, validate_flow_definition
from apps.auth_app.write_authorization import authorize_write
from apps.core.exceptions import APIError
from apps.core.modules import module_enabled
from apps.logs.audit import snapshot, write_audit
from apps.permissions.permissions import has_permission_code
from .attachments import attach_files, validate_files
from .relations import validate_relations
from .models import OnlineFormRecord
from .validators import validate_definition, validate_record


INPUT_TYPES = {'text': 'text', 'textarea': 'text', 'select': 'text', 'number': 'integer',
               'decimal': 'decimal', 'date': 'date', 'boolean': 'boolean'}


def check_inputs(flow, definition):
    try:
        validate_flow_definition(flow.definition)
    except ModelValidationError as error:
        raise ValidationError(error.messages) from error
    if flow.definition.get('schema_version') != 2:
        raise ValidationError('表单审批需要 V2 流程和显式输入登记')
    fields = {field['key']: field['type'] for field in definition['fields']}
    if any(INPUT_TYPES.get(fields.get(item['key'])) != item['type'] for item in flow.definition['inputs']):
        raise ValidationError('表单顶层字段与流程输入类型不一致')


def freeze_flow(form):
    if not form.approval_flow_code:
        return None
    if not module_enabled('approvals'):
        raise ValidationError('请先启用审批模块')
    flow = ApprovalFlow.objects.select_for_update().filter(
        code=form.approval_flow_code, tenant_id=form.tenant_id, status='published').first()
    if flow is None:
        raise ValidationError('当前租户没有该编码的已发布流程')
    check_inputs(flow, form.definition)
    return flow


def audit(request, row, before):
    write_audit(request=request, resource='online_record', identifier=row.pk, action='update',
                before=before, after=snapshot('online_record', row))


def sync_approval(application, request):
    row = OnlineFormRecord.objects.select_for_update(of=('self',)).select_related('form').filter(pk=application.business_record_id).first()
    if (row is None or row.approval_request_id != application.pk or row.approval_status != 'pending'
            or row.tenant_id != application.tenant_id or row.owner_id != application.applicant_id
            or row.form.approval_flow_id != application.flow_id or row.form.approval_flow_version != application.flow_version
            or application.status not in {'approved', 'rejected', 'cancelled'}):
        raise APIError('表单审批关联或状态已变化，请管理员检查', status_code=409)
    before = snapshot('online_record', row)
    row.approval_status = application.status
    row.version += 1
    row.save(update_fields=['approval_status', 'version', 'updated_at'])
    audit(request, row, before)


@transaction.atomic
def record_action(request, code, identifier, operation):
    if not module_enabled('online_forms') or not module_enabled('approvals'):
        raise NotFound()
    if not isinstance(request.data, dict) or type(request.data.get('version')) is not int or request.data['version'] < 1:
        raise ValidationError({'version': '必须提交正整数版本号'})
    actor = authorize_write(request, 'online_form:record_' + ('submit' if operation == 'submit' else 'withdraw'))
    queryset = OnlineFormRecord.objects.filter(form__code=code, owner=actor)
    candidate = queryset.filter(pk=identifier).first()
    if candidate is None:
        raise NotFound()
    # 与审批中心统一按申请→记录锁；撤回不能持记录锁再等待审批终审。
    application = None
    if operation == 'withdraw' and candidate.approval_request_id:
        application = ApprovalRequest.objects.select_for_update().filter(pk=candidate.approval_request_id).first()
    row = queryset.select_for_update(of=('self',)).select_related('form').filter(pk=identifier).first()
    if row is None:
        raise NotFound()
    if row.version != request.data['version']:
        raise APIError('记录已变化，请刷新后重试', status_code=409)
    if operation == 'withdraw':
        if (application is None or row.approval_request_id != application.pk or row.approval_status != 'pending'
                or application.status != 'pending' or application.applicant_id != actor.pk
                or application.tenant_id != row.tenant_id):
            raise APIError('当前记录没有可撤回的审批', status_code=409)
        application.status = 'cancelled'
        application.decided_at = timezone.now()
        application.save(update_fields=['status', 'decided_at', 'updated_at'])
        application.steps.filter(status='pending').update(status='cancelled', updated_at=timezone.now())
        ApprovalAction.objects.create(request=application, actor=actor, action='cancel', tenant_id=row.tenant_id)
        sync_approval(application, request)
        row.refresh_from_db()
        return row
    if row.approval_status not in {'draft', 'rejected', 'cancelled'}:
        raise APIError('当前记录不能重复提交审批', status_code=409)
    flow = ApprovalFlow.objects.filter(pk=row.form.approval_flow_id, tenant_id=row.tenant_id,
        version=row.form.approval_flow_version, status__in=['published', 'archived']).first()
    if flow is None:
        raise ValidationError('该表单版本没有可用的冻结审批流程')
    check_inputs(flow, row.definition_snapshot)
    normalized = validate_record(row.definition_snapshot, row.data)
    inputs = input_data(flow.definition, {item['key']: normalized.get(item['key']) for item in flow.definition['inputs']})
    files = validate_files(row.definition_snapshot, normalized, actor, row.tenant_id, lock=True)
    validate_relations(row.definition_snapshot, normalized, actor, row.tenant_id, lock=True)
    frozen = {'form_id': str(row.form_id), 'release_number': row.form.release_number,
              'record_version': row.version, 'definition': deepcopy(row.definition_snapshot), 'data': normalized}
    if len(json.dumps(frozen, ensure_ascii=False).encode('utf-8')) > 131072:
        raise ValidationError('表单审批快照不能超过128KiB')
    application = ApprovalRequest.objects.create(
        title='表单审批：' + str(row.pk), content='在线表单记录审批', request_type='other',
        applicant=actor, assignee=actor, flow=flow, flow_version=flow.version, extra_data=inputs,
        business_module='online_forms', business_record_id=row.pk, business_snapshot=frozen, tenant_id=row.tenant_id)
    ApprovalFileReference.objects.bulk_create([ApprovalFileReference(request=application, file_id=value, tenant_id=row.tenant_id)
                                             for value in sorted(set(files.values()))])
    users = enter_next(application, initial=True)
    before = snapshot('online_record', row)
    row.data = normalized
    row.approval_status = 'pending'
    row.approval_request = application
    row.version += 1
    row.save(update_fields=['data', 'approval_status', 'approval_request', 'version', 'updated_at'])
    attach_files(row, files)
    audit(request, row, before)
    from apps.core.events import enqueue_event
    enqueue_event(topic='notification.created', event_key=f'approval:{application.pk}:submitted',
        payload={'recipient_ids': [str(user.pk) for user in users], 'title': '待审批：' + application.title,
                 'content': '', 'notification_type': 'approval', 'link': '/approvals',
                 'data': {'request_id': str(application.pk)}}, request=request)
    return row


def redact_approval_snapshot(application, actor, data):
    """审批参与资格不授予动态业务值或附件访问；读取权限实时复核且只投影已知类型。"""
    empty = {**data, 'title': '在线表单审批', 'extra_data': {}, 'business_snapshot': {}}
    if not module_enabled('online_forms') or not has_permission_code(actor, 'online_form:record_read'):
        return empty
    frozen = application.business_snapshot
    if not isinstance(frozen, dict) or not isinstance(frozen.get('definition'), dict) or not isinstance(frozen.get('data'), dict):
        return empty
    try:
        # 校验原始结构，未知嵌套属性不可因任意 JSON 快照而绕过协议。
        definition = validate_definition(frozen['definition'])
        normalized = validate_record(definition, frozen['data'])
    except (ValidationError, KeyError, TypeError, ValueError):
        return empty
    def project(definition, values):
        result = {}
        for field in definition.get('fields', []):
            key, kind = field['key'], field['type']
            if kind in {'file', 'relation'}:
                continue  # 审批参与资格不扩展附件或业务关联权限；UUID、名称、默认值均不复制。
            value = values.get(key)
            if kind == 'detail':
                value = [project(field, item) for item in value or []]
            result[field['label'] + ' (' + key + ')'] = value
        return result
    return {**empty, 'business_snapshot': {'release_number': frozen.get('release_number'),
                                         'fields': project(definition, normalized)}}
