from django.conf import settings
from django.db import models
from apps.core.models import BaseModel


class OnlineForm(BaseModel):
    STATUS_CHOICES = [('draft', '草稿'), ('published', '已发布'), ('archived', '已归档')]
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='draft', db_index=True)
    version = models.PositiveIntegerField(default=1)
    definition = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='online_forms_created')
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='online_forms_published')
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [models.Index(fields=['status', 'code']), models.Index(fields=['created_by', 'status'])]


class OnlineFormRecord(BaseModel):
    form = models.ForeignKey(OnlineForm, on_delete=models.PROTECT, related_name='records')
    form_version = models.PositiveIntegerField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='online_form_records')
    data = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['form', 'owner', '-created_at'], name='online_record_owner'),
                   models.Index(fields=['form', 'form_version'])]
