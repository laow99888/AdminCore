"""显式通知目录及个人策略；偏好不产生人员、资源或外部渠道授权。"""
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import NotificationPreference

EVENTS = {
    'system.notice': {'label': '系统与安全通知', 'required': True},
    'approval.action': {'label': '审批待办与结果', 'required': True},
    'task.result': {'label': '任务运行结果', 'required': True},
    'announcement.update': {'label': '公告提醒', 'required': False},
    'template.message': {'label': '业务模板消息', 'required': False},
    'business.update': {'label': '业务更新提醒', 'required': False},
}
OPTIONAL_EVENTS = tuple(key for key, value in EVENTS.items() if not value['required'])
CHANNELS = ('inapp', 'email', 'webhook', 'sms')
_CURRENT_TENANT = object()
TYPE_EVENTS = {'system': 'system.notice', 'approval': 'approval.action', 'task': 'task.result',
               'announcement': 'announcement.update'}


class DeliveryDeferred(Exception):
    def __init__(self, until):
        self.until = until
        super().__init__('recipient_quiet_hours')


def preference_for(user_id, tenant_id=_CURRENT_TENANT):
    return preference_queryset(tenant_id).filter(user_id=user_id).first()


def preference_queryset(tenant_id=_CURRENT_TENANT):
    from apps.core.tenancy import current_tenant_id, enabled
    if tenant_id is _CURRENT_TENANT:
        tenant_id = current_tenant_id() if enabled() else None
    return NotificationPreference.all_objects.filter(tenant_id=tenant_id)


def subscribed(preference, event_code, channel):
    if event_code not in EVENTS:
        raise ValueError('unregistered_notification_event')
    # 必须通知的站内副本不受任何个人策略影响。认证邮件完全不经过本模块。
    if EVENTS[event_code]['required'] and channel == 'inapp':
        return True
    if preference is None:
        return True
    return channel in preference.channels and (EVENTS[event_code]['required'] or event_code in preference.subscriptions)


def eligible_inapp_recipients(users, event_code, notification_type):
    event_code = event_code or TYPE_EVENTS.get(notification_type, 'system.notice')
    if event_code not in EVENTS:
        raise ValueError('unregistered_notification_event')
    if EVENTS[event_code]['required']:
        return users
    users = list(users)
    preferences = {row.user_id: row for row in preference_queryset().filter(user_id__in=[user.pk for user in users])}
    return [user for user in users if subscribed(preferences.get(user.pk), event_code, 'inapp')]


def quiet_until(preference, now=None):
    """站外免打扰结束时间；按墙钟分钟计算，显式处理 DST 回拨和不存在时间。"""
    if preference is None or not preference.quiet_enabled:
        return None
    now = now or timezone.now()
    zone = ZoneInfo(preference.timezone)
    local = now.astimezone(zone)
    minute = local.hour * 60 + local.minute
    start = preference.quiet_start.hour * 60 + preference.quiet_start.minute
    end = preference.quiet_end.hour * 60 + preference.quiet_end.minute
    if not (start <= minute < end if start < end else minute >= start or minute < end):
        return None
    # 最多跨 27 小时，逐 UTC 分钟找第一个不处于安静窗口的真实时刻。
    # 免去构造 DST 不存在本地时间，也不会在回拨窗口内提前发送。
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(27 * 60):
        local = candidate.astimezone(zone)
        value = local.hour * 60 + local.minute
        inside = start <= value < end if start < end else value >= start or value < end
        if not inside:
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError('invalid_quiet_window')
