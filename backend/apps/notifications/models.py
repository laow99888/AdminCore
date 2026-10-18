"""
通知系统模型
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.db import transaction
import hashlib
from datetime import time

from apps.core.models import BaseModel

User = get_user_model()


def default_notification_subscriptions():
    return ['announcement.update', 'template.message', 'business.update']


def default_notification_channels():
    return ['inapp', 'email', 'webhook', 'sms']


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
             dedupe_key=None, event_code=None):
        """批量创建站内通知的统一入口"""
        from apps.core.modules import module_enabled
        if not module_enabled('notifications') or not recipient_ids:
            return 0
        User = get_user_model()
        users = User.objects.filter(id__in=recipient_ids, is_active=True, is_service_account=False)
        from apps.core.tenancy import current_tenant_id, enabled
        tenant_id = current_tenant_id() if enabled() else None
        if tenant_id is not None:
            from apps.core.models import Tenant, TenantMembership
            if not Tenant.objects.filter(pk=tenant_id, status=Tenant.STATUS_ACTIVE).exists():
                return 0
            users = users.filter(pk__in=TenantMembership.objects.filter(
                tenant_id=tenant_id, is_active=True).values('user_id'))
        from .preferences import eligible_inapp_recipients
        users = eligible_inapp_recipients(users, event_code, notification_type)
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
        objs = [cls(recipient=user, tenant_id=tenant_id, title=title, content=content, notification_type=notification_type,
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


class MessageTemplate(BaseModel):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['code']
        constraints = [models.CheckConstraint(condition=models.Q(revision__gte=1), name='message_template_revision_valid')]


class MessageTemplateVersion(BaseModel):
    template = models.ForeignKey(MessageTemplate, on_delete=models.PROTECT, related_name='versions')
    number = models.PositiveIntegerField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    variables = models.JSONField(default=list)
    creator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-number']
        constraints = [models.UniqueConstraint(fields=['template', 'number'], name='message_template_version_unique')]


class MessageDelivery(BaseModel):
    CHANNELS = [('inapp', '站内通知'), ('email', 'SMTP 邮件'), ('webhook', 'Webhook'), ('sms', 'Twilio 短信')]
    STATUS_CHOICES = [('pending', '待发送'), ('sending', '发送中'), ('succeeded', '成功'), ('failed', '失败'), ('terminated', '已终止')]
    version = models.ForeignKey(MessageTemplateVersion, on_delete=models.PROTECT, related_name='deliveries')
    recipient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='message_deliveries')
    creator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_message_deliveries')
    channel = models.CharField(max_length=10, choices=CHANNELS)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    email_binding = models.CharField(max_length=64, blank=True)
    external_binding = models.CharField(max_length=64, blank=True)
    actor_session_version = models.PositiveIntegerField()
    actor_session_id = models.UUIDField(null=True)
    request_id = models.CharField(max_length=100, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=100, blank=True)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['status', 'created_at'])]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['pending', 'sending', 'succeeded', 'failed', 'terminated']), name='message_delivery_status_valid'),
            models.CheckConstraint(condition=models.Q(channel__in=['inapp', 'email', 'webhook', 'sms']), name='message_delivery_channel_valid'),
            models.CheckConstraint(condition=models.Q(attempts__lte=5), name='message_delivery_attempts_valid'),
        ]


class SmsDispatchFence(models.Model):
    """独立提交的短信意图。无外键，避免和派发事务的用户/投递锁形成等待。"""
    delivery_id = models.UUIDField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class NotificationPreference(BaseModel):
    """个人偏好按租户隔离；省略记录时沿用全部订阅、全部渠道。"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_preferences')
    subscriptions = models.JSONField(default=default_notification_subscriptions)
    channels = models.JSONField(default=default_notification_channels)
    quiet_enabled = models.BooleanField(default=False)
    quiet_start = models.TimeField(default=time(22, 0))
    quiet_end = models.TimeField(default=time(8, 0))
    timezone = models.CharField(max_length=64, default='Asia/Shanghai')
    business_delivery_mode = models.CharField(max_length=9, choices=[('immediate', '立即'), ('digest', '摘要')], default='immediate')
    digest_minutes = models.PositiveIntegerField(default=60)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'user'], condition=models.Q(tenant__isnull=False),
                                    name='notification_pref_tenant_user'),
            models.UniqueConstraint(fields=['user'], condition=models.Q(tenant__isnull=True),
                                    name='notification_pref_global_user'),
            models.CheckConstraint(condition=models.Q(revision__gte=1), name='notification_pref_revision'),
            models.CheckConstraint(condition=models.Q(business_delivery_mode__in=['immediate', 'digest']), name='notification_pref_mode'),
            models.CheckConstraint(condition=models.Q(digest_minutes__in=[60, 1440]), name='notification_pref_digest_minutes'),
        ]


class BusinessNotice(BaseModel):
    """只保存受信业务引用，不将业务正文复制到摘要或队列。"""
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='business_notices')
    resource = models.CharField(max_length=32)
    object_id = models.UUIDField()
    event_key = models.CharField(max_length=64, unique=True)
    due_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    state = models.CharField(max_length=10, choices=[('pending', '待摘要'), ('published', '已入箱'), ('suppressed', '已抑制')], default='pending')
    notification = models.ForeignKey(Notification, on_delete=models.SET_NULL, null=True, related_name='business_notices')

    class Meta:
        ordering = ['due_at', 'pk']
        indexes = [models.Index(fields=['state', 'due_at'], name='business_notice_due')]
        constraints = [models.CheckConstraint(condition=models.Q(state__in=['pending', 'published', 'suppressed']), name='business_notice_state')]
