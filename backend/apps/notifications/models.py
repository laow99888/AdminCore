"""
通知系统模型
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.db import transaction
import hashlib

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
    dedupe_key = models.CharField(max_length=180, unique=True, null=True, blank=True, verbose_name='事件去重键')

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
    def push(cls, recipient_ids, title, content='', notification_type='system', link='', data=None, sender=None,
             dedupe_key=None):
        """批量创建站内通知的统一入口"""
        from apps.core.modules import module_enabled
        if not module_enabled('notifications') or not recipient_ids:
            return 0
        User = get_user_model()
        users = User.objects.filter(id__in=recipient_ids)
        if dedupe_key:
            count = 0
            with transaction.atomic():
                for user in users:
                    key = hashlib.sha256(f'{dedupe_key}:{user.id}'.encode()).hexdigest()
                    _, created = cls.objects.get_or_create(dedupe_key=key, defaults={
                        'recipient': user, 'title': title, 'content': content,
                        'notification_type': notification_type, 'link': link, 'data': data, 'sender': sender,
                    })
                    count += int(created)
            return count
        objs = [cls(recipient=user, title=title, content=content, notification_type=notification_type,
                    link=link, data=data, sender=sender) for user in users]
        cls.objects.bulk_create(objs)
        return len(objs)


class Announcement(BaseModel):
    """全员公告的共享发布记录，不为每位用户复制个人通知。"""
    STATUS_CHOICES = [('draft', '草稿'), ('published', '已发布'), ('withdrawn', '已撤回')]
    CONTENT_FORMAT_CHOICES = [('plain', '纯文本'), ('html', 'HTML')]
    title = models.CharField(max_length=200)
    content = models.TextField()
    content_format = models.CharField(max_length=5, choices=CONTENT_FORMAT_CHOICES, default='plain')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    version = models.PositiveIntegerField(default=1)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_announcements')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='updated_announcements')

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['status', '-published_at', '-id'], name='announcement_public_order')]
        constraints = [models.CheckConstraint(condition=models.Q(status__in=['draft', 'published', 'withdrawn']), name='announcement_valid_status'),
                       models.CheckConstraint(condition=models.Q(content_format__in=['plain', 'html']), name='announcement_valid_format')]
