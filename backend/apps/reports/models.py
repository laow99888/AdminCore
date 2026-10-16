from django.conf import settings
from django.db import models
from apps.core.models import BaseModel


class ReportDefinition(BaseModel):
    STATUS_CHOICES = [('draft', '草稿'), ('published', '已发布'), ('archived', '已归档')]
    KIND_CHOICES = [('report', '报表'), ('dashboard', '大屏')]
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default='report')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='draft', db_index=True)
    version = models.PositiveIntegerField(default=1)
    definition = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reports_created')
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='reports_published')
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [models.Index(fields=['status', 'code']), models.Index(fields=['created_by', 'status'])]
