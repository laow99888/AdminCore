"""删除用户时退休其头像，保留存储记录供现有保留期任务清理。"""
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import User
from django.contrib.auth.signals import user_logged_in


@receiver(user_logged_in, dispatch_uid='auth.admin_session_version')
def remember_admin_session_version(sender, request, user, **kwargs):
    # 与撤销设备共用用户锁：不能在认证之后把已撤销的快照登记为新会话。
    from django.db import transaction
    from django.contrib.auth import logout
    with transaction.atomic():
        current = User.objects.select_for_update().get(pk=user.pk)
        if not current.is_active or current.session_version != user.session_version or current.password != user.password:
            logout(request)
            return
        request.session['admincore_session_version'] = current.session_version



@receiver(pre_delete, sender=User, dispatch_uid='auth.retire_deleted_user_avatar')
def retire_deleted_user_avatar(sender, instance, **kwargs):
    # Collector 在事务内发送 pre_delete；沿用上传的 User → File 行锁顺序。
    # 删除对象可能早于并发上传被读取，必须重新查询当前绑定。
    avatar_id = User.objects.select_for_update().filter(pk=instance.pk).values_list('avatar_file_id', flat=True).first()
    if avatar_id:
        from apps.files.models import FileModel
        avatar = FileModel.objects.filter(pk=avatar_id, purpose='avatar').first()
        if avatar:
            # 与替换/移除相同：事务内先解除当前绑定，再退休文件。
            User.objects.filter(pk=instance.pk).update(avatar_file=None)
            avatar.soft_delete()
