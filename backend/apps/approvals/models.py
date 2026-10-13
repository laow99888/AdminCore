"""
审批流程模型
"""

from django.db import models
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel

User = get_user_model()


class ApprovalRequest(BaseModel):
    """审批申请（当前为单级审批：提交 -> 指定审批人处理）"""
    TYPE_CHOICES = [
        ('leave', '请假'),
        ('purchase', '采购'),
        ('permission', '权限申请'),
        ('other', '其他'),
    ]
    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已通过'),
        ('rejected', '已驳回'),
        ('cancelled', '已撤回'),
    ]

    title = models.CharField(max_length=200, verbose_name='标题')
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other', verbose_name='申请类型')
    content = models.TextField(verbose_name='申请内容')
    applicant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applied_requests', verbose_name='申请人')
    assignee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pending_approvals', verbose_name='当前审批人')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='processed_requests', verbose_name='处理人')
    decision_comment = models.TextField(blank=True, verbose_name='审批意见')
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name='处理时间')
    extra_data = models.JSONField(null=True, blank=True, verbose_name='附加数据')

    class Meta:
        verbose_name = '审批申请'
        verbose_name_plural = '审批申请'
        indexes = [
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['applicant', 'status']),
        ]

    def __str__(self):
        return f'{self.applicant.username} - {self.title} [{self.status}]'

    @transaction.atomic
    def decide(self, user, approved, comment='', request=None):
        """执行审批决策并通知申请人"""
        from django.utils import timezone
        from apps.core.events import enqueue_event

        self.status = 'approved' if approved else 'rejected'
        self.decided_by = user
        self.decision_comment = comment
        self.decided_at = timezone.now()
        changed = type(self).objects.filter(pk=self.pk, status='pending', assignee=user).update(
            status=self.status, decided_by=user, decision_comment=comment,
            decided_at=self.decided_at, updated_at=timezone.now())
        if not changed:
            self.refresh_from_db()
            return False

        enqueue_event(
            topic='notification.created',
            event_key=f'approval:{self.id}:decision:{self.status}',
            payload={
                'recipient_ids': [str(self.applicant_id)],
                'title': f'您的申请「{self.title}」已{"通过" if approved else "驳回"}',
                'content': comment,
                'notification_type': 'approval',
                'link': '/approvals',
                'data': {'request_id': str(self.id), 'status': self.status},
            },
            request=request,
        )
        return True
