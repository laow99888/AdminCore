"""显式已实现的渠道；没有任意函数路径、目标地址或动态导入。"""
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.utils.crypto import salted_hmac

from .models import Notification


def email_binding(user):
    return salted_hmac('business-notification-email', user.email.strip().lower()).hexdigest()


def enabled(channel):
    return channel == 'inapp' or channel == 'email' and bool(
        settings.NOTIFICATION_EMAIL_ENABLED and settings.EMAIL_HOST and settings.DEFAULT_FROM_EMAIL)


def inapp(delivery, recipient):
    if Notification.push(recipient_ids=[recipient.pk], title=delivery.subject, content=delivery.body,
                         notification_type='system', sender=delivery.creator, dedupe_key='message:' + str(delivery.pk)) not in (0, 1):
        raise RuntimeError('inapp_delivery_failed')


def email(delivery, recipient):
    message = EmailMessage(delivery.subject, delivery.body, settings.DEFAULT_FROM_EMAIL, [recipient.email],
        headers={'Message-ID': f'<admincore-message-{delivery.pk}@admincore.invalid>'},
        connection=get_connection(timeout=min(settings.EMAIL_TIMEOUT, 20)))
    if message.send(fail_silently=False) != 1:
        raise RuntimeError('email_delivery_failed')


CHANNELS = {'inapp': inapp, 'email': email}
