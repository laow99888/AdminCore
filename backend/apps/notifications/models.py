"""
通知系统模型
"""

from django.db import models
from django.contrib.auth import get_user_model

from apps.core.models import BaseModel

User = get_user_model()


class Notification(BaseModel):
    """站内通知"""
    TYPE_CHOICES = [
        ('system', '系统通知'),
        ('approval', '审批通知'),
        ('task', '任务通知'),
        ('announcement', '公告'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', verbose_name='接收者')
    title = models.CharField(max_length=200, verbose_name='标题')
    content = models.TextField(blank=True, verbose_name='内容')
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='system', verbose_name='通知类型')
    is_read = models.BooleanField(default=False, verbose_name='是否已读')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='已读时间')
    link = models.CharField(max_length=255, blank=True, verbose_name='跳转链接（前端路由）')
    data = models.JSONField(null=True, blank=True, verbose_name='附加数据')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications', verbose_name='发送者（系统通知为空）')

    class Meta:
        verbose_name = '通知'
        verbose_name_plural = '通知'
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.recipient.username} - {self.title}'

    def mark_read(self):
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at', 'updated_at'])

    @classmethod
    def push(cls, recipient_ids, title, content='', notification_type='system', link='', data=None, sender=None):
        """批量创建站内通知的统一入口"""
        if not recipient_ids:
            return 0
        User = get_user_model()
        users = User.objects.filter(id__in=recipient_ids)
        objs = [
            cls(recipient=user, title=title, content=content, notification_type=notification_type,
                link=link, data=data, sender=sender)
            for user in users
        ]
        cls.objects.bulk_create(objs)
        return len(objs)
