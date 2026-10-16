from django.db import models


class IPPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    allow = models.JSONField(default=list)
    deny = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name='ip_policy_singleton'),
            models.CheckConstraint(condition=models.Q(version__gte=1), name='ip_policy_version_valid'),
        ]
