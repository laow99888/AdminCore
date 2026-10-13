"""
审批流程视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.core.schema import envelope

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.logs.models import OperationLog
from apps.core.events import enqueue_event
from apps.core.idempotency import with_idempotency

from .models import ApprovalRequest
from .serializers import ApprovalCreateSerializer, ApprovalDecisionSerializer, ApprovalRequestSerializer
from apps.core.personnel import candidates, people_response, picker_departments, PeoplePageSerializer, PickerDepartmentsSerializer, PeopleQuerySerializer


@extend_schema_view(
    create=extend_schema(responses={201: envelope('ApprovalCreatedResponse', ApprovalRequestSerializer())}),
    approve=extend_schema(request=ApprovalDecisionSerializer, responses=envelope('ApprovalApprovedResponse', ApprovalRequestSerializer())),
    reject=extend_schema(request=ApprovalDecisionSerializer, responses=envelope('ApprovalRejectedResponse', ApprovalRequestSerializer())),
    cancel=extend_schema(request=None, responses=envelope('ApprovalCancelledResponse', ApprovalRequestSerializer())),
)
class ApprovalRequestViewSet(viewsets.GenericViewSet,
                             viewsets.mixins.ListModelMixin,
                             viewsets.mixins.RetrieveModelMixin,
                             viewsets.mixins.CreateModelMixin):
    """审批中心：发起申请 / 待办 / 已办 / 我的申请 / 审批决策"""
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'request_type']
    search_fields = ['title', 'content', 'applicant__username']
    ordering_fields = ['created_at', 'decided_at']
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ApprovalRequest.objects.none()
        queryset = ApprovalRequest.objects.select_related('applicant', 'assignee', 'decided_by')
        box = self.request.query_params.get('box')
        if box == 'todo':
            # 待办：我是审批人且未处理
            return queryset.filter(assignee=self.request.user, status='pending')
        if box == 'done':
            # 已办：我处理过的申请
            return queryset.filter(decided_by=self.request.user)
        if box == 'sent':
            # 我发起的申请
            return queryset.filter(applicant=self.request.user)
        # 默认（无 box）：与我相关的申请（我是审批人或申请人）
        from django.db.models import Q
        return queryset.filter(Q(assignee=self.request.user) | Q(applicant=self.request.user))

    def get_serializer_class(self):
        if self.action == 'create':
            return ApprovalCreateSerializer
        return ApprovalRequestSerializer

    @extend_schema(parameters=[PeopleQuerySerializer], responses=envelope('ApprovalAssigneesResponse', PeoplePageSerializer()), filters=False)
    @action(detail=False, methods=['get'], url_path='assignees')
    def assignees(self, request):
        return people_response(request, self)

    @extend_schema(parameters=[], responses=envelope('ApprovalPickerDepartmentsResponse', PickerDepartmentsSerializer()), filters=False)
    @action(detail=False, methods=['get'], url_path='assignee-departments')
    def assignee_departments(self, request):
        return Response({'code': 200, 'message': 'success', 'data': picker_departments(request.user)},
                        headers={'Cache-Control': 'private, no-store'})

    def _log(self, request, action, instance, description):
        OperationLog.objects.create(
            user=request.user,
            action=action,
            resource='approval',
            resource_id=str(instance.id),
            description=description,
            ip_address=request.META.get('REMOTE_ADDR', ''),
        )

    def create(self, request, *args, **kwargs):
        def action():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                assignee = get_user_model().objects.select_for_update().filter(pk=serializer.validated_data['assignee'].pk, is_active=True).first()
                if assignee is None or not candidates(request.user).filter(pk=assignee.pk).exists():
                    raise ValidationError({'assignee_id': '审批人不在可选范围内，请重新选择'})
                serializer.validated_data['assignee'] = assignee
                application = ApprovalRequest.objects.create(applicant=request.user, **serializer.validated_data)
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

    def _decide(self, request, approved):
        application = self.get_object()
        if application.status != 'pending':
            return Response({'code': 400, 'message': f'该申请当前状态为 {application.get_status_display()}，无法处理',
                             'data': None}, status=status.HTTP_400_BAD_REQUEST)
        if application.assignee_id != request.user.id:
            return Response({'code': 403, 'message': '只有当前审批人可以处理该申请', 'data': None},
                            status=status.HTTP_403_FORBIDDEN)

        comment_serializer = ApprovalDecisionSerializer(data=request.data)
        comment_serializer.is_valid(raise_exception=True)
        if not application.decide(request.user, approved, comment_serializer.validated_data['comment'], request=request):
            return Response({'code': 400, 'message': '申请已由其他请求处理', 'data': None}, status=400)

        self._log(request, 'update', application,
                  f'{"Approve" if approved else "Reject"} request: {application.title}')
        return Response({'code': 200, 'message': '已通过' if approved else '已驳回',
                         'data': ApprovalRequestSerializer(application).data})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """通过申请"""
        if self.get_object().assignee_id != request.user.id:
            return Response({'code': 403, 'message': '只有当前审批人可以处理该申请', 'data': None}, status=403)
        return with_idempotency(request, f'approvals:{pk}:approve', lambda: self._decide(request, approved=True))

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """驳回申请"""
        if self.get_object().assignee_id != request.user.id:
            return Response({'code': 403, 'message': '只有当前审批人可以处理该申请', 'data': None}, status=403)
        return with_idempotency(request, f'approvals:{pk}:reject', lambda: self._decide(request, approved=False))

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """撤回自己的待审批申请"""
        application = self.get_object()
        if application.applicant_id != request.user.id:
            return Response({'code': 403, 'message': '只能撤回自己发起的申请', 'data': None},
                            status=status.HTTP_403_FORBIDDEN)
        if application.status != 'pending':
            return Response({'code': 400, 'message': '该申请已处理，无法撤回', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone
        application.status = 'cancelled'
        application.decided_at = timezone.now()
        changed = ApprovalRequest.objects.filter(pk=application.pk, status='pending', applicant=request.user).update(
            status='cancelled', decided_at=application.decided_at, updated_at=timezone.now())
        if not changed:
            return Response({'code': 400, 'message': '申请已处理，无法撤回', 'data': None}, status=400)
        self._log(request, 'delete', application, f'Cancel approval request: {application.title}')
        return Response({'code': 200, 'message': '申请已撤回',
                         'data': ApprovalRequestSerializer(application).data})
