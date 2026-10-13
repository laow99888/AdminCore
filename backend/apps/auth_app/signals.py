"""删除用户时退休其头像，保留存储记录供现有保留期任务清理。"""
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import User


@receiver(pre_delete, sender=User, dispatch_uid='auth.retire_deleted_user_avatar')
def retire_deleted_user_avatar(sender, instance, **kwargs):
    # Collector 在事务内发送 pre_delete；沿用上传的 User → File 行锁顺序。
    # 删除对象可能早于并发上传被读取，必须重新查询当前绑定。
    avatar_id = User.objects.select_for_update().filter(pk=instance.pk).values_list('avatar_file_id', flat=True).first()
    if avatar_id:
        from apps.files.models import FileModel
        avatar = FileModel.objects.filter(pk=avatar_id, purpose='avatar').first()
        if avatar:
            avatar.soft_delete()
