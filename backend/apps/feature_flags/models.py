import uuid
from django.db import models
from apps.core.models import BaseModel


class FeatureFlag(BaseModel):
    key = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=1000, blank=True)
    enabled = models.BooleanField(default=False)
    # 万分比；同一开关、同一用户始终落入同一桶，扩量不会挤走已有用户。
    rollout = models.PositiveSmallIntegerField(default=0)
    seed = models.UUIDField(default=uuid.uuid4, editable=False)
    included_users = models.JSONField(default=list)
    excluded_users = models.JSONField(default=list)
    roles = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['key']
        constraints = [
            models.CheckConstraint(condition=models.Q(rollout__lte=10000), name='feature_flag_rollout_valid'),
            models.CheckConstraint(condition=models.Q(version__gte=1), name='feature_flag_version_valid'),
        ]
