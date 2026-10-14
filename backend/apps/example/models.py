from django.conf import settings
from django.db import models
from apps.core.models import BaseModel


class WorkItem(BaseModel):
    title = models.CharField(max_length=120)
    notes = models.CharField(max_length=2000, blank=True)
    status = models.CharField(max_length=10, choices=[('open', '待处理'), ('done', '已完成')], default='open')
    priority = models.CharField(max_length=10, choices=[('normal', '普通'), ('high', '高')], default='normal')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='example_items')
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['creator', 'status', '-created_at'], name='example_owner_status')]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['open', 'done']), name='example_status_valid'),
            models.CheckConstraint(condition=models.Q(priority__in=['normal', 'high']), name='example_priority_valid'),
            models.CheckConstraint(condition=models.Q(version__gte=1), name='example_version_valid'),
        ]
