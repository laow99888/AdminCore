"""历史清理级联删除请求时，同步清理私有导出产物。"""
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import BusinessExportRequest


@receiver(post_delete, sender=BusinessExportRequest)
def remove_export_artifact(sender, instance, **kwargs):
    if instance.artifact:
        storage, name = instance.artifact.storage, instance.artifact.name
        transaction.on_commit(lambda: storage.delete(name))
