"""
审批流程视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.core.schema import envelope
from apps.core.query_budget import QueryBudgetListMixin

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.generics import get_object_or_404
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Prefetch
from django.utils import timezone

from apps.auth_app.write_authorization import authorize_write
from apps.core.events import enqueue_event
from apps.core.idempotency import with_idempotency
from apps.core.exceptions import APIError

from .models import ApprovalAction, ApprovalCC, ApprovalFlow, ApprovalRequest, ApprovalStep
from .serializers import (ApprovalCreateSerializer, ApprovalDecisionSerializer, ApprovalFlowDesignSerializer,
                          ApprovalFlowSerializer, ApprovalRequestSerializer, ApprovalWorkflowActionSerializer)
from apps.core.personnel import candidates, people_response, picker_departments, PeoplePageSerializer, PickerDepartmentsSerializer, PeopleQuerySerializer


@extend_schema_view(
    create=extend_schema(responses={201: envelope('ApprovalCreatedResponse', ApprovalRequestSerializer())}),
    approve=extend_schema(request=ApprovalDecisionSerializer, responses=envelope('ApprovalApprovedResponse', ApprovalRequestSerializer())),
    reject=extend_schema(request=ApprovalDecisionSerializer, responses=envelope('ApprovalRejectedResponse', ApprovalRequestSerializer())),
    cancel=extend_schema(request=None, responses=envelope('ApprovalCancelledResponse', ApprovalRequestSerializer())),
    cc=extend_schema(request=ApprovalWorkflowActionSerializer, responses=envelope('ApprovalCCResponse', ApprovalRequestSerializer())),
    add_sign=extend_schema(request=ApprovalWorkflowActionSerializer, responses=envelope('ApprovalAddSignResponse', ApprovalRequestSerializer())),
    transfer=extend_schema(request=ApprovalWorkflowActionSerializer, responses=envelope('ApprovalTransferResponse', ApprovalRequestSerializer())),
    delegate=extend_schema(request=ApprovalWorkflowActionSerializer, responses=envelope('ApprovalDelegateResponse', ApprovalRequestSerializer())),
    repair_step=extend_schema(request=ApprovalWorkflowActionSerializer, responses=envelope('ApprovalRepairStepResponse', ApprovalRequestSerializer())),
)
class ApprovalRequestViewSet(QueryBudgetListMixin, viewsets.GenericViewSet,
                             viewsets.mixins.ListModelMixin,
                             viewsets.mixins.RetrieveModelMixin,
                             viewsets.mixins.CreateModelMixin):
    """审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策"""
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'request_type']
    search_fields = ['title', 'content', 'applicant__username']
    ordering_fields = ['created_at', 'decided_at']
    ordering = ['-created_at']
    list_query_choices = {'box': ('', 'todo', 'done', 'sent', 'cc', 'exceptions')}

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ApprovalRequest.objects.none()
        queryset = ApprovalRequest.objects.select_related('applicant', 'assignee', 'decided_by', 'flow')
        if self.action in {'list', 'retrieve'}:
            queryset = queryset.prefetch_related(
                Prefetch('steps', queryset=ApprovalStep.objects.select_related('assignee', 'delegated_to').order_by('sequence', 'created_at')),
                Prefetch('cc_recipients', queryset=ApprovalCC.objects.select_related('user')))
        box = self.request.query_params.get('box')
        if box == 'exceptions':
            if not (self.request.user.is_staff or self.request.user.is_superuser):
                return queryset.none()
            return queryset.filter(status='pending').filter(
                Q(assignee__is_active=False) | Q(steps__status='pending', steps__assignee__isnull=True)
                | Q(steps__status='pending', steps__assignee__is_active=False)).distinct()
        if box == 'cc':
            return queryset.filter(cc_recipients__user=self.request.user).distinct()
        if box == 'todo':
            # 待办：兼容旧单级审批人与工作流步骤审批人/受托人
            return queryset.filter(
                Q(status='pending', assignee=self.request.user)
                | Q(status='pending', steps__assignee=self.request.user, steps__status='pending')
                | Q(status='pending', steps__delegated_to=self.request.user, steps__status='pending')
            ).distinct()
        if box == 'done':
            # 已办：兼容最终决定人、工作流步骤处理人和动作操作者
            return queryset.filter(
                Q(decided_by=self.request.user)
                | Q(steps__acted_by=self.request.user)
                | Q(actions__actor=self.request.user)
            ).distinct()
        if box == 'sent':
            # 我发起的申请
            return queryset.filter(applicant=self.request.user)
        # 默认（无 box）：与我相关的申请（我是审批人或申请人）
        return queryset.filter(
            Q(assignee=self.request.user) | Q(applicant=self.request.user)
            | Q(steps__assignee=self.request.user, steps__status='pending')
            | Q(steps__delegated_to=self.request.user, steps__status='pending')
            | Q(steps__acted_by=self.request.user) | Q(cc_recipients__user=self.request.user)
        ).distinct()

    def _locked_application(self, pk):
        # PostgreSQL 不支持在 DISTINCT 查询上加 FOR UPDATE，先锁主行再复核可见范围。
        application = get_object_or_404(ApprovalRequest.objects.select_for_update(), pk=pk)
        get_object_or_404(self.get_queryset(), pk=application.pk)
        if application.status != 'pending':
            raise APIError('该申请已结束，不能修改参与人', status_code=409)
        return application

    def _targets(self, request, identifiers):
        identifiers = set(identifiers)
        if not identifiers:
            raise ValidationError('请选择有效人员')
        authorize_write(request, related_users=identifiers)
        users = list(candidates(request.user).filter(pk__in=identifiers, is_active=True))
        if len(users) != len(identifiers):
            raise ValidationError('目标人员不在可选范围内，请重新选择')
        return users

    def _notice(self, application, recipients, key, title):
        recipients = sorted({str(pk) for pk in recipients if pk})
        if recipients:
            enqueue_event(topic='notification.created', event_key=f'approval:{application.pk}:{key}',
                payload={'recipient_ids': recipients, 'title': title, 'content': '',
                         'notification_type': 'approval', 'link': '/approvals',
                         'data': {'request_id': str(application.pk)}}, request=self.request)

    def _action_record(self, application, action, *, target=None, step=None, comment=''):
        record = ApprovalAction.objects.create(request=application, step=step, actor=self.request.user,
            action=action, target_user=target, comment=comment)
        if target:
            self._notice(application, [target.pk], str(record.pk), f'审批参与人已调整：{application.title}')
        self._log(self.request, 'update', application)
        return record

    def get_serializer_class(self):
        if self.action == 'create':
            return ApprovalCreateSerializer
        return ApprovalRequestSerializer

    def _workflow_steps(self, application, flow):
        from .models import validate_flow_definition
        try:
            validate_flow_definition(flow.definition)
        except Exception as exc:
            raise ValidationError('流程定义不受支持，请管理员修正后重新发布') from exc
        nodes = {node['id']: node for node in flow.definition['nodes']}
        edges = {edge['from']: edge['to'] for edge in flow.definition.get('edges', [])}
        current = next(node for node in flow.definition['nodes'] if node['type'] == 'start')
        sequence = 0
        while current['type'] != 'end':
            next_id = edges.get(current['id'])
            if not next_id:
                break
            current = nodes[next_id]
            if current['type'] in {'user', 'parallel', 'or'}:
                mode = current.get('mode', 'all' if current['type'] in {'user', 'parallel'} else 'any')
                requested_ids = current.get('assignee_ids', [])
                found = {str(user.pk): user for user in get_user_model().objects.filter(pk__in=requested_ids, is_active=True)}
                users = [found[user_id] for user_id in requested_ids if user_id in found]
                if not users or len(users) != len(set(requested_ids)):
                    from apps.core.error_i18n import error_text
                    raise ValidationError({'flow_id': error_text('流程节点 {node_id} 包含无效审批人', node_id=current['id'])})
                for user in users:
                    ApprovalStep.objects.create(request=application, node_key=current['id'], kind=current['type'],
                                                mode=mode, sequence=sequence, assignee=user,
                                                candidates=[str(row.pk) for row in users])
                application.current_node = current['id']
                application.assignee = users[0]
                break
            sequence += 1
        application.save(update_fields=['current_node', 'assignee', 'updated_at'])

    def _advance_workflow(self, application):
        flow = application.flow
        nodes = {node['id']: node for node in flow.definition['nodes']}
        edges = {edge['from']: edge['to'] for edge in flow.definition.get('edges', [])}
        current_id = application.current_node
        current = nodes.get(current_id)
        target_id = edges.get(current_id) if current else None
        while target_id:
            target = nodes[target_id]
            if target['type'] == 'end':
                application.status = 'approved'
                application.decided_by = application.decided_by or application.applicant
                application.decided_at = timezone.now()
                application.current_node = target_id
                application.save(update_fields=['status', 'decided_by', 'decided_at', 'current_node', 'updated_at'])
                return
            if target['type'] in {'user', 'parallel', 'or'}:
                requested_ids = target.get('assignee_ids', [])
                found = {str(user.pk): user for user in get_user_model().objects.filter(pk__in=requested_ids, is_active=True)}
                users = [found[user_id] for user_id in requested_ids if user_id in found]
                if len(users) != len(requested_ids) or not users:
                    raise APIError('下一节点包含停用或已删除的审批人，请管理员调整后重试', status_code=409)
                mode = target.get('mode', 'all' if target['type'] in {'user', 'parallel'} else 'any')
                for user in users:
                    ApprovalStep.objects.create(request=application, node_key=target['id'], kind=target['type'],
                                                mode=mode, sequence=(max(application.steps.values_list('sequence', flat=True), default=0) + 1),
                                                assignee=user, candidates=[str(row.pk) for row in users])
                application.current_node = target['id']
                application.assignee = users[0]
                application.workflow_version += 1
                application.save(update_fields=['current_node', 'assignee', 'workflow_version', 'updated_at'])
                self._notice(application, [user.pk for user in users],
                    f'node:{target_id}:{application.workflow_version}', f'待审批：{application.title}')
                return
            target_id = edges.get(target_id)

    def _workflow_decide(self, request, application, approved, comment):
        step = ApprovalStep.objects.select_for_update().filter(request=application, status='pending').filter(
            Q(assignee=request.user) | Q(delegated_to=request.user)).order_by('sequence', 'created_at').first()
        if step is None:
            return Response({'code': 403, 'message': '只有当前流程节点审批人可以处理该申请', 'data': None}, status=403)
        step.status = 'approved' if approved else 'rejected'
        step.acted_by = request.user
        step.acted_at = timezone.now()
        step.comment = comment
        step.version += 1
        step.save(update_fields=['status', 'acted_by', 'acted_at', 'comment', 'version', 'updated_at'])
        ApprovalAction.objects.create(request=application, step=step, actor=request.user,
                                      action='approve' if approved else 'reject', comment=comment)
        siblings = ApprovalStep.objects.filter(request=application, node_key=step.node_key)
        if not approved:
            application.steps.filter(status='pending').update(status='cancelled', updated_at=timezone.now())
            application.status = 'rejected'
            application.decided_by = request.user
            application.decision_comment = comment
            application.decided_at = timezone.now()
            application.save(update_fields=['status', 'decided_by', 'decision_comment', 'decided_at', 'updated_at'])
        elif step.mode == 'any':
            siblings.filter(status='pending').update(status='skipped', updated_at=timezone.now())
            self._advance_workflow(application)
        elif not siblings.filter(status='pending').exists():
            self._advance_workflow(application)
        if application.status in {'approved', 'rejected'}:
            self._notice(application, [application.applicant_id], f'result:{application.status}',
                f'申请已通过：{application.title}' if approved else f'申请已驳回：{application.title}')
        return None

    @extend_schema(parameters=[PeopleQuerySerializer], responses=envelope('ApprovalAssigneesResponse', PeoplePageSerializer()), filters=False)
    @action(detail=False, methods=['get'], url_path='assignees')
    def assignees(self, request):
        return people_response(request, self)

    @extend_schema(parameters=[], responses=envelope('ApprovalPickerDepartmentsResponse', PickerDepartmentsSerializer()), filters=False)
    @action(detail=False, methods=['get'], url_path='assignee-departments')
    def assignee_departments(self, request):
        return Response({'code': 200, 'message': 'success', 'data': picker_departments(request.user)},
                        headers={'Cache-Control': 'private, no-store'})

    def _log(self, request, action, instance, description='', before=None):
        from apps.logs.audit import snapshot, write_audit
        write_audit(request=request, resource='approval', identifier=instance.pk, action=action,
                    before=before, after=snapshot('approval', instance))

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        related = ((serializer.validated_data['assignee'].pk,) if 'assignee' in serializer.validated_data else ())
        authorize_write(request, related_users=related)
        assignee = serializer.validated_data.get('assignee')
        if assignee is not None:
            assignee = get_user_model().objects.filter(pk=assignee.pk, is_active=True).first()
            if assignee is None or not candidates(request.user).filter(pk=assignee.pk).exists():
                raise ValidationError({'assignee_id': '审批人不在可选范围内，请重新选择'})
            serializer.validated_data['assignee'] = assignee

        def action():
            with transaction.atomic():
                flow = serializer.validated_data.pop('flow', None)
                if flow is not None:
                    first_ids = next((n.get('assignee_ids', []) for n in flow.definition['nodes'] if n['type'] in {'user', 'parallel', 'or'}), [])
                    assignee = get_user_model().objects.filter(pk=first_ids[0], is_active=True).first() if first_ids else None
                    if assignee is None:
                        raise ValidationError({'flow_id': '流程首个审批节点没有有效审批人'})
                    serializer.validated_data['assignee'] = assignee
                application = ApprovalRequest.objects.create(applicant=request.user, flow=flow,
                    flow_version=flow.version if flow else None, **serializer.validated_data)
                if flow:
                    self._workflow_steps(application, flow)
                enqueue_event(
                    topic='notification.created', event_key=f'approval:{application.id}:submitted',
                    payload={'recipient_ids': ([str(pk) for pk in application.steps.values_list('assignee_id', flat=True)]
                                              if flow else [str(application.assignee_id)]),
                             'title': f'{request.user.username} 提交了审批申请「{application.title}」',
                             'content': application.content[:200], 'notification_type': 'approval',
                             'link': '/approvals', 'data': {'request_id': str(application.id)}}, request=request,
                )
                self._log(request, 'create', application, f'Submit approval request: {application.title}')
            return Response({'code': 200, 'message': '申请已提交', 'data': ApprovalRequestSerializer(application).data},
                            status=status.HTTP_201_CREATED)
        return with_idempotency(request, 'approvals:create', action)

    @transaction.atomic
    def _decide(self, request, approved):
        application = self.get_object()
        application = ApprovalRequest.objects.select_for_update().get(pk=application.pk)
        if application.status != 'pending':
            from apps.core.error_i18n import error_text
            return Response({'code': 400, 'message': error_text('该申请当前状态为 {status}，无法处理', status=error_text(application.get_status_display())),
                             'data': None}, status=status.HTTP_400_BAD_REQUEST)
        if application.flow_id:
            comment_serializer = ApprovalDecisionSerializer(data=request.data)
            comment_serializer.is_valid(raise_exception=True)
            result = self._workflow_decide(request, application, approved, comment_serializer.validated_data['comment'])
            if result:
                return result
            self._log(request, 'update', application)
            return Response({'code': 200, 'message': '已通过' if approved else '已驳回',
                             'data': ApprovalRequestSerializer(application).data})
        if application.assignee_id != request.user.id:
            return Response({'code': 403, 'message': '只有当前审批人可以处理该申请', 'data': None},
                            status=status.HTTP_403_FORBIDDEN)

        comment_serializer = ApprovalDecisionSerializer(data=request.data)
        comment_serializer.is_valid(raise_exception=True)
        from apps.logs.audit import snapshot
        before = snapshot('approval', application)
        if not application.decide(request.user, approved, comment_serializer.validated_data['comment'], request=request):
            return Response({'code': 400, 'message': '申请已由其他请求处理', 'data': None}, status=400)

        self._log(request, 'update', application,
                  before=before)
        return Response({'code': 200, 'message': '已通过' if approved else '已驳回',
                         'data': ApprovalRequestSerializer(application).data})

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        """通过申请"""
        authorize_write(request)
        current = self.get_object()
        if not current.flow_id and current.assignee_id != request.user.id:
            return Response({'code': 403, 'message': '只有当前审批人可以处理该申请', 'data': None}, status=403)
        return with_idempotency(request, f'approvals:{pk}:approve', lambda: self._decide(request, approved=True))

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def reject(self, request, pk=None):
        """驳回申请"""
        authorize_write(request)
        current = self.get_object()
        if not current.flow_id and current.assignee_id != request.user.id:
            return Response({'code': 403, 'message': '只有当前审批人可以处理该申请', 'data': None}, status=403)
        return with_idempotency(request, f'approvals:{pk}:reject', lambda: self._decide(request, approved=False))

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel(self, request, pk=None):
        """撤回自己的待审批申请"""
        authorize_write(request)
        application = self.get_object()
        application = ApprovalRequest.objects.select_for_update().get(pk=application.pk)
        if application.applicant_id != request.user.id:
            return Response({'code': 403, 'message': '只能撤回自己发起的申请', 'data': None},
                            status=status.HTTP_403_FORBIDDEN)
        if application.status != 'pending':
            return Response({'code': 400, 'message': '该申请已处理，无法撤回', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone
        from apps.logs.audit import snapshot
        before = snapshot('approval', application)
        application.status = 'cancelled'
        application.decided_at = timezone.now()
        changed = ApprovalRequest.objects.filter(pk=application.pk, status='pending', applicant=request.user).update(
            status='cancelled', decided_at=application.decided_at, updated_at=timezone.now())
        if not changed:
            return Response({'code': 400, 'message': '申请已处理，无法撤回', 'data': None}, status=400)
        application.steps.filter(status='pending').update(status='cancelled', updated_at=timezone.now())
        self._log(request, 'delete', application, before=before)
        return Response({'code': 200, 'message': '申请已撤回',
                         'data': ApprovalRequestSerializer(application).data})

    def _target_action(self, request, pk, operation):
        serializer = ApprovalWorkflowActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target = self._targets(request, [data['target_user_id']] if data.get('target_user_id') else [])[0]

        def execute():
            application = self._locked_application(pk)
            steps = application.steps.select_for_update().filter(status='pending', node_key=application.current_node)
            if data.get('step_id') and (request.user.is_staff or request.user.is_superuser):
                step = steps.filter(pk=data['step_id']).first()
            else:
                step = steps.filter(assignee=request.user).first()
                if step is None and operation == 'add_sign':
                    if request.user.is_staff or request.user.is_superuser:
                        step = steps.order_by('sequence', 'created_at').first()
                    else:
                        step = steps.filter(delegated_to=request.user).first()
            if step is None:
                raise PermissionDenied('只有当前节点审批人或管理员可以修改该步骤')
            expected = data.get('expected_version')
            if expected is not None and expected != step.version:
                raise APIError('审批步骤已变化，请刷新后重试', status_code=409)
            if operation in {'add_sign', 'transfer'} and application.steps.filter(node_key=step.node_key, assignee=target).exists():
                raise APIError('目标人员已在当前审批节点中', status_code=409)
            if operation == 'add_sign':
                step = ApprovalStep.objects.create(request=application, node_key=step.node_key, kind=step.kind,
                    mode=step.mode, sequence=step.sequence, assignee=target, candidates=step.candidates)
            elif operation == 'transfer':
                old_assignee = step.assignee_id
                step.assignee = target
                step.delegated_to = None
                step.version += 1
                step.save(update_fields=['assignee', 'delegated_to', 'version', 'updated_at'])
                if application.assignee_id == old_assignee or old_assignee is None:
                    application.assignee = target
            else:
                if target.pk == step.assignee_id:
                    raise ValidationError('不能委托给当前审批人自己')
                step.delegated_to = target
                step.version += 1
                step.save(update_fields=['delegated_to', 'version', 'updated_at'])
            application.workflow_version += 1
            application.save(update_fields=['assignee', 'workflow_version', 'updated_at'])
            self._action_record(application, operation, target=target, step=step, comment=data['comment'])
            return Response({'code': 200, 'message': '操作成功', 'data': ApprovalRequestSerializer(application).data})
        return with_idempotency(request, f'approvals:{pk}:{operation.replace("_", "-")}', execute)

    @action(detail=True, methods=['post'], url_path='repair-step')
    @transaction.atomic
    def repair_step(self, request, pk=None):
        serializer = ApprovalWorkflowActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target = self._targets(request, [data['target_user_id']] if data.get('target_user_id') else [])[0]
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied()
        if not data.get('step_id') or data.get('expected_version') is None:
            raise ValidationError('修复步骤必须提供步骤和当前版本')

        def execute():
            application = get_object_or_404(ApprovalRequest.objects.select_for_update(), pk=pk, status='pending')
            step = get_object_or_404(application.steps.select_for_update(), pk=data['step_id'], status='pending', node_key=application.current_node)
            if step.version != data['expected_version']:
                raise APIError('审批步骤已变化，请刷新后重试', status_code=409)
            if step.assignee_id and get_user_model().objects.filter(pk=step.assignee_id, is_active=True).exists():
                raise ValidationError('仅允许修复审批人缺失或停用的待处理步骤')
            if application.steps.filter(node_key=step.node_key, assignee=target).exists():
                raise APIError('目标人员已在当前审批节点中', status_code=409)
            old = step.assignee_id
            step.assignee, step.delegated_to, step.version = target, None, step.version + 1
            step.save(update_fields=['assignee', 'delegated_to', 'version', 'updated_at'])
            if application.assignee_id == old or not application.assignee.is_active:
                application.assignee = target
            application.workflow_version += 1
            application.save(update_fields=['assignee', 'workflow_version', 'updated_at'])
            self._action_record(application, 'transfer', target=target, step=step, comment=data['comment'])
            return Response({'code': 200, 'message': '操作成功', 'data': ApprovalRequestSerializer(application).data})
        return with_idempotency(request, f'approvals:{pk}:repair-step', execute)

    @action(detail=True, methods=['post'], url_path='add-sign')
    @transaction.atomic
    def add_sign(self, request, pk=None):
        return self._target_action(request, pk, 'add_sign')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def transfer(self, request, pk=None):
        return self._target_action(request, pk, 'transfer')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def delegate(self, request, pk=None):
        return self._target_action(request, pk, 'delegate')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cc(self, request, pk=None):
        serializer = ApprovalWorkflowActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users = self._targets(request, serializer.validated_data.get('user_ids', []))

        def execute():
            application = self._locked_application(pk)
            may_cc = (request.user.is_staff or request.user.is_superuser
                or application.applicant_id == request.user.pk or application.assignee_id == request.user.pk
                or application.steps.filter(status='pending').filter(
                    Q(assignee=request.user) | Q(delegated_to=request.user)).exists())
            if not may_cc:
                raise PermissionDenied('当前用户无权抄送该申请')
            for user in users:
                _, created = ApprovalCC.objects.get_or_create(request=application, user=user, defaults={'created_by': request.user})
                if created:
                    self._action_record(application, 'cc', target=user, comment=serializer.validated_data['comment'])
            return Response({'code': 200, 'message': '抄送成功', 'data': ApprovalRequestSerializer(application).data})
        return with_idempotency(request, f'approvals:{pk}:cc', execute)


class ApprovalFlowViewSet(QueryBudgetListMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = ApprovalFlow.objects.select_related('created_by', 'published_by').all()
    serializer_class = ApprovalFlowSerializer
    filterset_fields = ['status']
    ordering_fields = ['created_at', 'code', 'name', 'status', 'version']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'put', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ApprovalFlow.objects.none()
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            return super().get_queryset().filter(status='published') if self.action == 'list' else ApprovalFlow.objects.none()
        return super().get_queryset()

    def get_serializer_class(self):
        return ApprovalFlowDesignSerializer if self.action in {'create', 'update'} else ApprovalFlowSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        authorize_write(request, admin=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flow = serializer.save(created_by=request.user, version=1)
        return Response({'code': 200, 'message': '流程草稿已创建', 'data': ApprovalFlowSerializer(flow).data}, status=201)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        authorize_write(request, admin=True)
        flow = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=kwargs['pk'])
        if flow.status != 'draft':
            return Response({'code': 400, 'message': '已发布流程不可直接修改，请新建版本', 'data': None}, status=400)
        serializer = self.get_serializer(flow, data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.pop('version', None) != flow.version:
            raise APIError('流程已变化，请刷新后重试', status_code=409)
        flow = serializer.save(version=flow.version + 1)
        return Response({'code': 200, 'message': '流程草稿已更新', 'data': ApprovalFlowSerializer(flow).data})

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def publish(self, request, pk=None):
        authorize_write(request, admin=True)
        flow = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        if 'version' in request.data and request.data['version'] != flow.version:
            raise APIError('流程已变化，请刷新后重试', status_code=409)
        if flow.status != 'draft':
            return Response({'code': 400, 'message': '只有草稿可以发布', 'data': None}, status=400)
        from .models import validate_flow_definition
        validate_flow_definition(flow.definition)
        flow.status = 'published'
        flow.published_by = request.user
        flow.published_at = timezone.now()
        flow.save(update_fields=['status', 'published_by', 'published_at', 'updated_at'])
        return Response({'code': 200, 'message': '流程已发布', 'data': ApprovalFlowSerializer(flow).data})

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def archive(self, request, pk=None):
        authorize_write(request, admin=True)
        flow = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        flow.status = 'archived'
        flow.save(update_fields=['status', 'updated_at'])
        return Response({'code': 200, 'message': '流程已归档', 'data': ApprovalFlowSerializer(flow).data})
