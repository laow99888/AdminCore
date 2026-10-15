"""版本固定、身份复核、有界投递及安全失败记录。"""
from datetime import timedelta
from string import Template
import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.events import enqueue_event
from apps.core.models import OutboxEvent
from apps.core.modules import module_enabled
from apps.core.personnel import candidates
from apps.permissions.permissions import has_permission_code
from apps.logs.audit import write_audit
from .models import MessageTemplate, MessageTemplateVersion, MessageDelivery
from .message_channels import CHANNELS, enabled, email_binding
from .external_channels import binding, TerminalDeliveryError


def validate_content(subject, body, variables):
    if '\r' in subject or '\n' in subject:
        raise ValidationError('标题不能包含换行')
    if len(variables) != len(set(variables)) or any(not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', key) for key in variables):
        raise ValidationError('变量须为唯一的小写字母开头标识')
    declared = set(variables)
    used = set()
    for text in (subject, body):
        parsed = Template(text)
        if not parsed.is_valid():
            raise ValidationError('占位符格式无效，请使用 ${name}；字面 $ 写为 $$')
        used.update(parsed.get_identifiers())
    if used != declared:
        raise ValidationError('声明变量须恰好匹配标题和正文中的占位符')


def render(version, values):
    if set(values) != set(version.variables) or any(not isinstance(value, str) or len(value) > 2000 for value in values.values()):
        raise ValidationError('须提供全部声明变量的文本值，每项最多 2000 字符')
    subject, body = [Template(text).substitute(values) for text in (version.subject, version.body)]
    if not subject.strip() or len(subject) > 200 or len(body) > 20000 or '\r' in subject or '\n' in subject:
        raise ValidationError('渲染结果超限或标题含换行')
    return subject, body


def template_values(row, version):
    import hashlib
    return {'id': row.pk, 'code': row.code, 'enabled': row.enabled, 'revision': row.revision,
            'variables': version.variables, 'content_sha256': hashlib.sha256((version.subject + '\n' + version.body).encode()).hexdigest()}


@transaction.atomic
def save_template(request, actor, data, identifier=None):
    validate_content(data['subject'], data['body'], data['variables'])
    before = None
    if identifier:
        from rest_framework.generics import get_object_or_404
        row = get_object_or_404(MessageTemplate.objects.select_for_update(), pk=identifier)
        if row.revision != data['revision']:
            from apps.core.system_views import VersionConflict
            raise VersionConflict()
        before = template_values(row, row.versions.get(number=row.revision))
        if data['code'] != row.code:
            raise ValidationError('模板编码创建后不能修改')
        row.name, row.enabled, row.revision = data['name'], data['enabled'], row.revision + 1
        row.save(update_fields=['name', 'enabled', 'revision', 'updated_at'])
    else:
        if data['revision'] != 0:
            raise ValidationError('新模板 revision 必须为 0')
        row = MessageTemplate.objects.create(code=data['code'], name=data['name'], enabled=data['enabled'])
    version = MessageTemplateVersion.objects.create(template=row, number=row.revision, subject=data['subject'],
        body=data['body'], variables=data['variables'], creator=actor)
    write_audit(request=request, actor=actor, resource='message_template', identifier=row.pk,
                action='create' if before is None else 'update', before=before, after=template_values(row, version))
    return row


@transaction.atomic
def submit(request, actor, template_id, revision, recipient_ids, channels, values):
    from rest_framework.generics import get_object_or_404
    # 固定用户锁顺序，两个管理员互相发送也不能各自持对方需要的锁。
    locked = list(get_user_model().objects.select_for_update().filter(pk__in=[actor.pk, *recipient_ids]).order_by('pk'))
    from .announcement_services import authorize
    actor = authorize(request, 'template:send')
    session = None
    if request.auth is not None:
        from apps.auth_app.sessions import locked_request_session
        session = locked_request_session(request, actor)
    row = get_object_or_404(MessageTemplate.objects.select_for_update(), pk=template_id)
    if not row.enabled or row.revision != revision:
        raise ValidationError('模板停用或版本已变化，请重新预览')
    version = row.versions.get(number=revision)
    subject, body = render(version, values)
    if any(not enabled(channel) for channel in channels):
        raise ValidationError('所选渠道未启用或未配置，未登记任何发送')
    allowed = set(candidates(actor).filter(pk__in=recipient_ids).values_list('pk', flat=True))
    users = [user for user in locked if user.pk in allowed]
    if len(users) != len(recipient_ids):
        raise ValidationError('收件人不在当前可选范围或已停用')
    if 'email' in channels and any(not user.email_verified or not user.email or user.verified_email.strip().lower() != user.email.strip().lower() for user in users):
        raise ValidationError('邮件收件人必须具有已验证的当前邮箱')
    external_bindings = {}
    for user in users:
        for channel in set(channels) & {'sms', 'webhook'}:
            try:
                external_bindings[user.pk, channel] = binding(channel, user)
            except ValueError:
                raise ValidationError('短信收件人尚未完成部署管理员核验登记') from None
    if 'sms' in channels and (not body.strip() or len(body) > 1600):
        raise ValidationError('短信正文须为 1 到 1600 字符')
    deliveries = []
    for user in users:
        for channel in channels:
            delivery = MessageDelivery.objects.create(version=version, recipient=user, creator=actor,
                channel=channel, subject=subject, body=body, email_binding=email_binding(user) if channel == 'email' else '',
                external_binding=external_bindings.get((user.pk, channel), ''),
                actor_session_version=actor.session_version, actor_session_id=session.pk if session else None, request_id=request.request_id,
                expires_at=timezone.now() + timedelta(hours=24))
            enqueue_event('notification.delivery', 'message:' + str(delivery.pk), {'delivery_id': str(delivery.pk)}, request=request)
            deliveries.append(delivery)
    write_audit(request=request, actor=actor, resource='message_delivery', action='create',
                after={'template_id': row.pk, 'revision': revision, 'channels': channels, 'count': len(deliveries)},
                results=[{'id': item.pk, 'status': 202} for item in deliveries])
    return deliveries


def deliver(payload):
    if set(payload) != {'delivery_id'}:
        raise ValueError('invalid_delivery_event')
    row = MessageDelivery.objects.filter(pk=payload['delivery_id']).first()
    if row is None:
        raise ValueError('delivery_missing')
    if row.status in ('succeeded', 'terminated') or row.attempts >= 5:
        return
    users = {user.pk: user for user in get_user_model().objects.select_for_update().filter(pk__in=[row.creator_id, row.recipient_id], is_active=True).order_by('pk')}
    # 用户删除也会 SET_NULL 更新投递；先锁用户再锁已有投递，避免反向持锁。
    # of=self 防止 JOIN 提前取得模板锁，所有入口保持 user→session→template。
    row = MessageDelivery.objects.select_for_update(of=('self',)).select_related('version__template').get(pk=row.pk)
    actor, user = users.get(row.creator_id), users.get(row.recipient_id)
    reason = ''
    if row.expires_at <= timezone.now(): reason = 'delivery_expired'
    elif not module_enabled('notifications'): reason = 'notifications_disabled'
    elif actor is None or actor.must_change_password or not (actor.is_staff or actor.is_superuser) or actor.session_version != row.actor_session_version or not has_permission_code(actor, 'template:send'): reason = 'sender_revoked'
    elif row.actor_session_id and not valid_sender_session(row, actor): reason = 'sender_session_revoked'
    elif user is None or not candidates(actor).filter(pk=user.pk).exists(): reason = 'recipient_unavailable'
    elif not MessageTemplate.objects.select_for_update().get(pk=row.version.template_id).enabled: reason = 'template_disabled'
    elif not enabled(row.channel): reason = 'channel_disabled'
    elif row.channel == 'email' and (not user.email_verified or email_binding(user) != row.email_binding or user.verified_email.strip().lower() != user.email.strip().lower()): reason = 'recipient_email_changed'
    elif row.channel in ('sms', 'webhook'):
        try:
            if binding(row.channel, user) != row.external_binding:
                reason = 'external_destination_changed'
        except ValueError:
            reason = 'external_destination_changed'
    if reason:
        row.status, row.last_error = 'terminated', reason
        row.save(update_fields=['status', 'last_error', 'updated_at'])
        return
    row.attempts += 1
    try:
        CHANNELS[row.channel](row, user)
    except TerminalDeliveryError:
        row.status, row.last_error = 'terminated', 'external_delivery_rejected_or_unknown'
    except Exception:
        row.status, row.last_error = 'failed', 'channel_delivery_failed'
    else:
        row.status, row.last_error, row.sent_at = 'succeeded', '', timezone.now()
    row.save(update_fields=['status', 'attempts', 'last_error', 'sent_at', 'updated_at'])
    # 返回失败状态，由 Outbox 在其事务中持久化并退避，不抛异常回滚投递失败行。
    return row.status == 'failed'


def valid_sender_session(row, actor):
    from apps.auth_app.models import AuthSession
    from apps.auth_app.sessions import idle_cutoff
    from rest_framework_simplejwt.utils import get_md5_hash_password
    session = AuthSession.objects.select_for_update().filter(pk=row.actor_session_id, user=actor).first()
    return bool(session and not session.revoked_at and session.expires_at > timezone.now()
                and session.last_seen_at > idle_cutoff()
                and session.session_version == actor.session_version and session.password_hash == get_md5_hash_password(actor.password))


@transaction.atomic
def retry_delivery(request, actor, identifier):
    from rest_framework.generics import get_object_or_404
    # 与派发器一致：先事件、按 UUID 排序的用户，最后已有投递。
    event = get_object_or_404(OutboxEvent.objects.select_for_update(), event_key='message:' + str(identifier))
    pending = get_object_or_404(MessageDelivery.objects, pk=identifier)
    list(get_user_model().objects.select_for_update().filter(
        pk__in=[actor.pk, pending.creator_id, pending.recipient_id]).order_by('pk'))
    from .announcement_services import authorize
    actor = authorize(request, 'template:send', lock=True)
    row = get_object_or_404(MessageDelivery.objects.select_for_update(), pk=identifier)
    if row.status != 'failed' or row.attempts >= 5 or row.expires_at <= timezone.now() or event.status != 'failed':
        raise ValidationError('仅允许期限内且次数未用尽的失败投递重试')
    if not enabled(row.channel) or not row.version.template.enabled:
        raise ValidationError('渠道或模板未启用')
    before = {'id': row.pk, 'status': row.status, 'attempts': row.attempts}
    row.status = 'pending'
    row.save(update_fields=['status', 'updated_at'])
    event.status, event.available_at = 'pending', timezone.now()
    event.save(update_fields=['status', 'available_at', 'updated_at'])
    write_audit(request=request, actor=actor, resource='message_delivery', identifier=row.pk,
                before=before, after={'id': row.pk, 'status': row.status, 'attempts': row.attempts})
    from apps.core.events import _dispatch_after_commit
    transaction.on_commit(_dispatch_after_commit)
    return row
