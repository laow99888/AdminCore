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
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auth_app.write_authorization import authorize_write
from apps.core.events import enqueue_event
from apps.core.idempotency import with_idempotency

from .models import ApprovalAction, ApprovalCC, ApprovalFlow, ApprovalRequest, ApprovalStep
from .serializers import (ApprovalCreateSerializer, ApprovalDecisionSerializer, ApprovalFlowDesignSerializer,
                          ApprovalFlowSerializer, ApprovalRequestSerializer, ApprovalWorkflowActionSerializer)
from apps.core.personnel import candidates, people_response, picker_departments, PeoplePageSerializer, PickerDepartmentsSerializer, PeopleQuerySerializer


@extend_schema_view(
    create=extend_schema(responses={201: envelope('ApprovalCreatedResponse', ApprovalRequestSerializer())}),
    approve=extend_schema(request=ApprovalDecisionSerializer, responses=envelope('ApprovalApprovedResponse', ApprovalRequestSerializer())),
    reject=extend_schema(request=ApprovalDecisionSerializer, responses=envelope('ApprovalRejectedResponse', ApprovalRequestSerializer())),
    cancel=extend_schema(request=None, responses=envelope('ApprovalCancelledResponse', ApprovalRequestSerializer())),
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
    list_query_choices = {'box': ('', 'todo', 'done', 'sent')}

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ApprovalRequest.objects.none()
        queryset = ApprovalRequest.objects.select_related('applicant', 'assignee', 'decided_by')
        box = self.request.query_params.get('box')
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
        ).distinct()

    def get_serializer_class(self):
        if self.action == 'create':
            return ApprovalCreateSerializer
        return ApprovalRequestSerializer

    def _workflow_steps(self, application, flow):
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
                mode = target.get('mode', 'all' if target['type'] in {'user', 'parallel'} else 'any')
                for user in users:
                    ApprovalStep.objects.create(request=application, node_key=target['id'], kind=target['type'],
                                                mode=mode, sequence=(max(application.steps.values_list('sequence', flat=True), default=0) + 1),
                                                assignee=user, candidates=[str(row.pk) for row in users])
                application.current_node = target['id']
                application.assignee = users[0]
                application.workflow_version += 1
                application.save(update_fields=['current_node', 'assignee', 'workflow_version', 'updated_at'])
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
                    payload={'recipient_ids': [str(application.assignee_id)],
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
        self._log(request, 'delete', application, before=before)
        return Response({'code': 200, 'message': '申请已撤回',
                         'data': ApprovalRequestSerializer(application).data})

    @action(detail=True, methods=['post'], url_path='add-sign')
    @transaction.atomic
    def add_sign(self, request, pk=None):
        authorize_write(request)
        serializer = ApprovalWorkflowActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = get_user_model().objects.filter(pk=serializer.validated_data.get('target_user_id'), is_active=True).first()
        if not target:
            return Response({'code': 403, 'message': '无权加签或目标用户无效', 'data': None}, status=403)
        authorize_write(request, related_users=[target.pk])

        def execute():
            application = ApprovalRequest.objects.select_for_update().get(pk=pk)
            if application.assignee_id != request.user.id and not request.user.is_staff:
                return Response({'code': 403, 'message': '无权加签或目标用户无效', 'data': None}, status=403)
            step = application.steps.select_for_update().filter(status='pending').order_by('sequence').first()
            if not step:
                return Response({'code': 400, 'message': '当前没有可加签节点', 'data': None}, status=400)
            new_step = ApprovalStep.objects.create(request=application, node_key=step.node_key, kind=step.kind,
                mode=step.mode, sequence=step.sequence, assignee=target, candidates=step.candidates)
            ApprovalAction.objects.create(request=application, step=new_step, actor=request.user, action='add_sign',
                                          target_user=target, comment=serializer.validated_data['comment'])
            return Response({'code': 200, 'message': '加签成功', 'data': ApprovalRequestSerializer(application).data})
        return with_idempotency(request, f'approvals:{pk}:add-sign', execute)

    @action(detail=True, methods=['post'], url_path='transfer')
    @transaction.atomic
    def transfer(self, request, pk=None):
        authorize_write(request)
        serializer = ApprovalWorkflowActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = get_user_model().objects.filter(pk=serializer.validated_data.get('target_user_id'), is_active=True).first()
        if not target:
            return Response({'code': 400, 'message': '当前用户不是待处理节点审批人或目标用户无效', 'data': None}, status=400)
        authorize_write(request, related_users=[target.pk])

        def execute():
            application = ApprovalRequest.objects.select_for_update().get(pk=pk)
            step = application.steps.select_for_update().filter(status='pending', assignee=request.user).first()
            if not step:
                return Response({'code': 400, 'message': '当前用户不是待处理节点审批人或目标用户无效', 'data': None}, status=400)
            expected = serializer.validated_data.get('expected_version')
            if expected is not None and expected != step.version:
                return Response({'code': 409, 'message': '审批步骤已变化，请刷新后重试', 'data': None}, status=409)
            step.assignee = target
            step.version += 1
            step.save(update_fields=['assignee', 'version', 'updated_at'])
            application.assignee = target
            application.workflow_version += 1
            application.save(update_fields=['assignee', 'workflow_version', 'updated_at'])
            ApprovalAction.objects.create(request=application, step=step, actor=request.user, action='transfer', target_user=target,
                                          comment=serializer.validated_data['comment'])
            return Response({'code': 200, 'message': '转办成功', 'data': ApprovalRequestSerializer(application).data})
        return with_idempotency(request, f'approvals:{pk}:transfer', execute)

    @action(detail=True, methods=['post'], url_path='delegate')
    @transaction.atomic
    def delegate(self, request, pk=None):
        authorize_write(request)
        serializer = ApprovalWorkflowActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = get_user_model().objects.filter(pk=serializer.validated_data.get('target_user_id'), is_active=True).first()
        if not target:
            return Response({'code': 400, 'message': '当前用户不是待处理节点审批人或目标用户无效', 'data': None}, status=400)
        authorize_write(request, related_users=[target.pk])

        def execute():
            application = ApprovalRequest.objects.select_for_update().get(pk=pk)
            step = application.steps.select_for_update().filter(status='pending', assignee=request.user).first()
            if not step:
                return Response({'code': 400, 'message': '当前用户不是待处理节点审批人或目标用户无效', 'data': None}, status=400)
            expected = serializer.validated_data.get('expected_version')
            if expected is not None and expected != step.version:
                return Response({'code': 409, 'message': '审批步骤已变化，请刷新后重试', 'data': None}, status=409)
            step.delegated_to = target
            step.version += 1
            step.save(update_fields=['delegated_to', 'version', 'updated_at'])
            ApprovalAction.objects.create(request=application, step=step, actor=request.user, action='delegate', target_user=target,
                                          comment=serializer.validated_data['comment'])
            return Response({'code': 200, 'message': '委托成功', 'data': ApprovalRequestSerializer(application).data})
        return with_idempotency(request, f'approvals:{pk}:delegate', execute)

    @action(detail=True, methods=['post'], url_path='cc')
    @transaction.atomic
    def cc(self, request, pk=None):
        authorize_write(request)
        serializer = ApprovalWorkflowActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users = list(get_user_model().objects.filter(pk__in=serializer.validated_data.get('user_ids', []), is_active=True))
        if not users:
            return Response({'code': 400, 'message': '请选择有效抄送人', 'data': None}, status=400)
        authorize_write(request, related_users=[user.pk for user in users])

        def execute():
            application = ApprovalRequest.objects.select_for_update().get(pk=pk)
            for user in users:
                _, created = ApprovalCC.objects.get_or_create(request=application, user=user, defaults={'created_by': request.user})
                if created:
                    ApprovalAction.objects.create(request=application, actor=request.user, action='cc', target_user=user,
                                                  comment=serializer.validated_data['comment'])
            return Response({'code': 200, 'message': '抄送成功', 'data': ApprovalRequestSerializer(application).data})
        return with_idempotency(request, f'approvals:{pk}:cc', execute)


class ApprovalFlowViewSet(QueryBudgetListMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = ApprovalFlow.objects.select_related('created_by', 'published_by').all()
    serializer_class = ApprovalFlowSerializer
    ordering_fields = ['created_at', 'code', 'name', 'status', 'version']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'put', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ApprovalFlow.objects.none()
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            return ApprovalFlow.objects.none()
        return super().get_queryset()

    def get_serializer_class(self):
        return ApprovalFlowDesignSerializer if self.action in {'create', 'update'} else ApprovalFlowSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        authorize_write(request, admin=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flow = serializer.save(created_by=request.user)
        return Response({'code': 200, 'message': '流程草稿已创建', 'data': ApprovalFlowSerializer(flow).data}, status=201)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        authorize_write(request, admin=True)
        flow = self.get_object()
        if flow.status != 'draft':
            return Response({'code': 400, 'message': '已发布流程不可直接修改，请新建版本', 'data': None}, status=400)
        serializer = self.get_serializer(flow, data=request.data)
        serializer.is_valid(raise_exception=True)
        flow = serializer.save(version=flow.version + 1)
        return Response({'code': 200, 'message': '流程草稿已更新', 'data': ApprovalFlowSerializer(flow).data})

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def publish(self, request, pk=None):
        authorize_write(request, admin=True)
        flow = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
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
