from django.conf import settings
from copy import deepcopy
from django.db import models
from apps.core.models import BaseModel


class OnlineForm(BaseModel):
    approval_flow_code = models.CharField(max_length=80, blank=True)
    approval_flow = models.ForeignKey('approvals.ApprovalFlow', on_delete=models.PROTECT, null=True, blank=True, related_name='online_form_releases')
    approval_flow_version = models.PositiveIntegerField(null=True, blank=True)
    STATUS_CHOICES = [('draft', '草稿'), ('published', '已发布'), ('archived', '已归档')]
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='draft', db_index=True)
    version = models.PositiveIntegerField(default=1)
    release_number = models.PositiveIntegerField(default=1)
    definition = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='online_forms_created')
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='online_forms_published')
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [models.Index(fields=['status', 'code']), models.Index(fields=['created_by', 'status'])]
        constraints = [
            models.UniqueConstraint(fields=['code', 'release_number'], name='online_form_release_unique'),
            models.UniqueConstraint(fields=['code'], condition=models.Q(status='draft'), name='online_form_one_draft'),
            models.UniqueConstraint(fields=['code'], condition=models.Q(status='published'), name='online_form_one_published'),
        ]


class OnlineFormRecord(BaseModel):
    approval_status = models.CharField(max_length=16, default='draft', choices=[('draft', '未送审'), ('pending', '审批中'), ('approved', '已通过'), ('rejected', '已驳回'), ('cancelled', '已撤回')])
    approval_request = models.ForeignKey('approvals.ApprovalRequest', on_delete=models.PROTECT, null=True, blank=True, related_name='online_form_records')
    form = models.ForeignKey(OnlineForm, on_delete=models.PROTECT, related_name='records')
    form_version = models.PositiveIntegerField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='online_form_records')
    data = models.JSONField(default=dict)
    definition_snapshot = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)

    def save(self, *args, **kwargs):
        if self._state.adding and not self.definition_snapshot:
            self.definition_snapshot = deepcopy(self.form.definition)
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['form', 'owner', '-created_at'], name='online_record_owner'),
                   models.Index(fields=['form', 'form_version'])]


class OnlineFormFileReference(BaseModel):
    """追加式绑定：移除当前附件也保留历史引用，供文件删除协议自动发现。"""
    record = models.ForeignKey(OnlineFormRecord, on_delete=models.PROTECT, related_name='file_references')
    file = models.ForeignKey('files.FileModel', on_delete=models.PROTECT, related_name='+')
    first_record_version = models.PositiveIntegerField()
    first_field_path = models.CharField(max_length=128)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['record', 'file'], name='online_record_file_unique')]
