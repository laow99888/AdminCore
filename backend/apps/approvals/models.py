"""
审批流程模型
"""

from django.db import models
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from uuid import UUID

from apps.core.models import BaseModel

User = get_user_model()


def validate_flow_definition(definition):
    """Validate the small, deterministic graph format used by the workflow API."""
    if not isinstance(definition, dict):
        raise ValidationError('流程定义必须是对象')
    nodes = definition.get('nodes')
    edges = definition.get('edges', [])
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 100:
        raise ValidationError('流程节点数量必须在 1 到 100 之间')
    if not isinstance(edges, list) or len(edges) > 300:
        raise ValidationError('流程连线数量不能超过 300')
    allowed = {'start', 'user', 'parallel', 'or', 'end'}
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) - {'id', 'type', 'name', 'assignee_ids', 'mode'}:
            raise ValidationError('流程节点包含未知字段')
        key, kind = node.get('id'), node.get('type')
        if not isinstance(key, str) or not key or len(key) > 64 or key in ids:
            raise ValidationError('流程节点标识必须唯一且有效')
        if not isinstance(kind, str) or kind not in allowed:
            raise ValidationError('流程节点类型不受支持')
        ids.add(key)
        if kind in {'user', 'parallel', 'or'}:
            assignees = node.get('assignee_ids')
            if not isinstance(assignees, list) or not assignees or len(assignees) > 100:
                raise ValidationError('审批节点必须配置审批人')
            if any(not isinstance(value, str) for value in assignees):
                raise ValidationError('审批人标识必须为字符串')
            try:
                if len({UUID(value) for value in assignees}) != len(assignees):
                    raise ValueError
            except (ValueError, AttributeError):
                raise ValidationError('审批人标识无效或重复') from None
            mode = node.get('mode', 'all' if kind in {'user', 'parallel'} else 'any')
            if not isinstance(mode, str) or mode not in {'all', 'any'}:
                raise ValidationError('审批节点模式只能是 all 或 any')
    kinds = {node['type'] for node in nodes}
    if kinds - allowed or sum(node['type'] == 'start' for node in nodes) != 1 or sum(node['type'] == 'end' for node in nodes) != 1:
        raise ValidationError('流程必须且只能包含一个开始节点和一个结束节点')
    adjacency = {key: [] for key in ids}
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) - {'from', 'to'}:
            raise ValidationError('流程连线包含未知字段')
        source, target = edge.get('from'), edge.get('to')
        if not isinstance(source, str) or not isinstance(target, str) or source not in ids or target not in ids or source == target:
            raise ValidationError('流程连线端点无效')
        adjacency[source].append(target)
    starts = [node['id'] for node in nodes if node['type'] == 'start'][0]
    ends = [node['id'] for node in nodes if node['type'] == 'end'][0]
    # 运行器只支持节点间单链；多人会签/或签在节点内部表达。
    incoming = {key: sum(values.count(key) for values in adjacency.values()) for key in ids}
    if (len(nodes) < 3 or any(len(adjacency[key]) != (0 if key == ends else 1) for key in ids)
            or any(incoming[key] != (0 if key == starts else 1) for key in ids)):
        raise ValidationError('当前流程仅支持开始到结束的单链，分支请使用会签或或签节点')
    if not adjacency[starts] or any(key != starts and not any(key in values for values in adjacency.values()) for key in ids if key != starts):
        raise ValidationError('流程节点必须从开始节点可达')
    if not any(ends in values for values in adjacency.values()):
        raise ValidationError('结束节点必须有前置节点')
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValidationError('流程连线不能形成环')
        if key in visited:
            return
        visiting.add(key)
        for child in adjacency[key]:
            visit(child)
        visiting.remove(key)
        visited.add(key)
    visit(starts)
    if visited != ids:
        raise ValidationError('流程存在从开始节点不可达的节点')
    return definition


class ApprovalFlow(BaseModel):
    STATUS_CHOICES = [('draft', '草稿'), ('published', '已发布'), ('archived', '已归档')]
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=80, unique=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    version = models.PositiveIntegerField(default=1)
    definition = models.JSONField(default=dict)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_approval_flows')
    published_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='published_approval_flows')
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'code'])]

    def clean(self):
        validate_flow_definition(self.definition)
        if self.status == 'published' and not self.published_at:
            raise ValidationError('已发布流程必须记录发布时间')


class ApprovalStep(BaseModel):
    STATUS_CHOICES = [('pending', '待处理'), ('approved', '已通过'), ('rejected', '已驳回'), ('skipped', '已跳过'), ('cancelled', '已取消')]
    MODE_CHOICES = [('all', '会签'), ('any', '或签')]
    request = models.ForeignKey('ApprovalRequest', on_delete=models.CASCADE, related_name='steps')
    node_key = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=[('user', '审批'), ('parallel', '会签'), ('or', '或签')], default='user')
    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default='all')
    sequence = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    assignee = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='approval_steps')
    candidates = models.JSONField(default=list)
    delegated_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='delegated_approval_steps')
    comment = models.TextField(blank=True)
    acted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='acted_approval_steps')
    acted_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['request', 'node_key', 'assignee'], name='unique_approval_step_assignee')]
        indexes = [models.Index(fields=['request', 'status', 'sequence']), models.Index(fields=['assignee', 'status'])]


class ApprovalCC(BaseModel):
    request = models.ForeignKey('ApprovalRequest', on_delete=models.CASCADE, related_name='cc_recipients')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='approval_ccs')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_approval_ccs')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['request', 'user'], name='unique_approval_cc_user')]


class ApprovalAction(BaseModel):
    ACTION_CHOICES = [('approve', '通过'), ('reject', '驳回'), ('add_sign', '加签'), ('transfer', '转办'), ('delegate', '委托'), ('cc', '抄送'), ('cancel', '撤回')]
    request = models.ForeignKey('ApprovalRequest', on_delete=models.CASCADE, related_name='actions')
    step = models.ForeignKey(ApprovalStep, on_delete=models.SET_NULL, null=True, blank=True, related_name='actions')
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='approval_actions')
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='targeted_approval_actions')
    comment = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=['request', 'created_at'])]


class ApprovalRequest(BaseModel):
    """审批申请：兼容单人审批和已发布的多级、会签、或签流程。"""
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
    applicant = models.ForeignKey(User, on_delete=models.PROTECT, related_name='applied_requests', verbose_name='申请人')
    assignee = models.ForeignKey(User, on_delete=models.PROTECT, related_name='pending_approvals', verbose_name='当前审批人')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='processed_requests', verbose_name='处理人')
    decision_comment = models.TextField(blank=True, verbose_name='审批意见')
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name='处理时间')
    extra_data = models.JSONField(null=True, blank=True, verbose_name='附加数据')
    flow = models.ForeignKey(ApprovalFlow, on_delete=models.PROTECT, null=True, blank=True, related_name='requests')
    flow_version = models.PositiveIntegerField(null=True, blank=True)
    current_node = models.CharField(max_length=64, blank=True)
    workflow_version = models.PositiveIntegerField(default=1)

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
