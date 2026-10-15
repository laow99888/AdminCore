"""显式配置的外部通知；不接受请求中的 URL、手机号、密钥或供应商路径。"""
import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
import hmac
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.utils import timezone
from django.utils.crypto import salted_hmac


class TerminalDeliveryError(Exception):
    """明确永久拒绝或结果不确定，不自动重发产生额外副作用。"""


class RetryDeliveryError(Exception):
    """对端明确拒绝，可按既有 Outbox 退避重试。"""


_resolver = ThreadPoolExecutor(max_workers=2, thread_name_prefix='notification-dns')
_resolver_slots = threading.BoundedSemaphore(2)
PHONE = re.compile(r'^\+[1-9][0-9]{7,14}$')


def config(channel):
    value = getattr(settings, 'NOTIFICATION_EXTERNAL_CHANNELS', {}).get(channel, {})
    return value if isinstance(value, dict) else {}


def webhook_url(value):
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.fragment or parts.query or parts.port not in (None, 443)
            or len(value) > 500 or any(ord(char) < 33 or ord(char) > 126 for char in value)
            or not re.fullmatch(r'[a-zA-Z0-9.-]+', parts.hostname)):
        raise ValueError('invalid_webhook_url')
    return parts


def enabled(channel):
    cfg = config(channel)
    if cfg.get('enabled') is not True:
        return False
    try:
        if channel == 'webhook':
            webhook_url(cfg['url'])
            key_id = cfg['active_key']
            keys = cfg['keys']
            return bool(re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', key_id) and key_id in keys
                        and isinstance(keys, dict) and 1 <= len(keys) <= 3
                        and all(re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', name)
                            and 32 <= len(secret.encode()) <= 256 for name, secret in keys.items()))
        if channel == 'sms':
            return bool(re.fullmatch(r'AC[a-fA-F0-9]{32}', cfg['account_sid'])
                        and re.fullmatch(r'[a-zA-Z0-9_-]{20,128}', cfg['auth_token']) and PHONE.fullmatch(cfg['from'])
                        and isinstance(cfg['recipients'], dict))
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return False


def validate_configuration():
    configs = getattr(settings, 'NOTIFICATION_EXTERNAL_CHANNELS', {})
    if not isinstance(configs, dict) or set(configs) - {'webhook', 'sms'}:
        raise ImproperlyConfigured('通知外部渠道配置格式无效')
    for channel, cfg in configs.items():
        allowed = {'enabled', 'url', 'active_key', 'keys'} if channel == 'webhook' else {
            'enabled', 'account_sid', 'auth_token', 'from', 'recipients'}
        if (not isinstance(cfg, dict) or type(cfg.get('enabled', False)) is not bool or set(cfg) - allowed
                or (cfg.get('enabled') and not enabled(channel))):
            raise ImproperlyConfigured('通知外部渠道已开启但配置无效：' + channel)
        if channel == 'sms' and cfg.get('enabled'):
            try:
                if len(cfg['recipients']) > 10000:
                    raise ValueError()
                for identifier, number in cfg['recipients'].items():
                    if str(UUID(identifier)) != identifier or not PHONE.fullmatch(number):
                        raise ValueError()
            except (ValueError, TypeError):
                raise ImproperlyConfigured('短信已核验收件人配置无效') from None
            if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql' and not getattr(settings, 'TESTING', False):
                raise ImproperlyConfigured('短信可靠投递需要 PostgreSQL')


def binding(channel, recipient):
    cfg = config(channel)
    if channel == 'webhook':
        value = cfg.get('url', '')
    else:
        number = cfg.get('recipients', {}).get(str(recipient.pk), '')
        if not isinstance(number, str) or not PHONE.fullmatch(number):
            raise ValueError('recipient_sms_unregistered')
        value = '\n'.join([cfg.get('account_sid', ''), cfg.get('from', ''), number])
    # 密钥轮换不使已登记任务失效；地址、账号或手机号改变则终止旧投递。
    return salted_hmac('external-notification-' + channel, value).hexdigest()


def public_address(host):
    if not _resolver_slots.acquire(blocking=False):
        raise RetryDeliveryError('dns_busy')
    future = _resolver.submit(socket.getaddrinfo, host, 443, 0, socket.SOCK_STREAM)
    future.add_done_callback(lambda _: _resolver_slots.release())
    try:
        addresses = future.result(timeout=3)
    except (FutureTimeout, OSError):
        raise RetryDeliveryError('dns_unavailable') from None
    ips = list(dict.fromkeys(item[4][0] for item in addresses))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise TerminalDeliveryError('destination_not_public')
    return ips[0]


def post(url, body, headers):
    """固定解析结果后建立 TLS；仍使用原域名验证证书和 SNI；无代理/跳转。"""
    parts = webhook_url(url)
    address = public_address(parts.hostname)
    connection = http.client.HTTPSConnection(parts.hostname, timeout=5, context=ssl.create_default_context())
    connection._create_connection = lambda target, timeout, source_address=None: socket.create_connection(
        (address, 443), timeout=timeout, source_address=source_address)
    def expire():
        if connection.sock:
            try:
                connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    deadline = threading.Timer(5, expire)
    deadline.daemon = True
    deadline.start()
    try:
        connection.request('POST', parts.path or '/', body=body, headers=headers)
        response = connection.getresponse()
        # 状态码即可裁定结果，绝不读取/记录可能包含手机号、密钥或任意大正文的响应。
        return response.status
    finally:
        deadline.cancel()
        connection.close()


def webhook(delivery, recipient):
    cfg = config('webhook')
    body = json.dumps({'id': str(delivery.pk), 'recipient_id': str(recipient.pk),
        'template': delivery.version.template.code, 'revision': delivery.version.number,
        'subject': delivery.subject, 'body': delivery.body}, ensure_ascii=False,
        separators=(',', ':')).encode()
    timestamp, key_id = str(int(time.time())), cfg['active_key']
    signature = hmac.new(cfg['keys'][key_id].encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    try:
        status = post(cfg['url'], body, {'Content-Type': 'application/json',
            'X-AdminCore-Key-Id': key_id, 'X-AdminCore-Timestamp': timestamp,
            'X-AdminCore-Event-Id': str(delivery.pk), 'X-AdminCore-Signature': 'sha256=' + signature})
    except (OSError, http.client.HTTPException):
        # 同一 delivery id 必须由接收端幂等处理，允许可靠事件继续重试。
        raise RetryDeliveryError('webhook_transport_failed') from None
    if status == 429 or 500 <= status < 600:
        raise RetryDeliveryError('webhook_rejected')
    if not 200 <= status < 300:
        raise TerminalDeliveryError('webhook_rejected_permanently')


def sms(delivery, recipient):
    cfg = config('sms')
    number = cfg['recipients'][str(recipient.pk)]
    body = urlencode({'To': number, 'From': cfg['from'], 'Body': delivery.body}).encode()
    authorization = base64.b64encode((cfg['account_sid'] + ':' + cfg['auth_token']).encode()).decode()
    if not sms_fence(delivery.pk):
        raise TerminalDeliveryError('sms_previous_outcome_unknown')
    try:
        status = post(f"https://api.twilio.com/2010-04-01/Accounts/{cfg['account_sid']}/Messages.json",
            body, {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Basic ' + authorization})
    except RetryDeliveryError:
        sms_fence(delivery.pk, release=True)  # DNS 在任何 POST 前失败，可以安全退避。
        raise
    except TerminalDeliveryError:
        raise
    except (OSError, http.client.HTTPException):
        # Twilio 创建接口没有已承诺的幂等键：断线/超时无法判断是否已计费，禁止自动重发。
        raise TerminalDeliveryError('sms_outcome_unknown') from None
    if status == 429:
        sms_fence(delivery.pk, release=True)
        raise RetryDeliveryError('sms_rate_limited')
    if status != 201:
        raise TerminalDeliveryError('sms_provider_rejected_or_unknown')


def sms_fence(identifier, *, release=False):
    """先在独立 PG 连接持久化意图，外层 Outbox 回滚/进程退出不能抹除。

    代价是提交意图后、实际发送前崩溃也会终止；运维对账后另建新投递。
    原 delivery id 永不绕过此屏障；不提供任意释放或强制重发接口。
    """
    if connection.vendor != 'postgresql':
        raise TerminalDeliveryError('sms_requires_postgresql')
    isolated = connection.copy(alias='notification_sms_fence')
    try:
        isolated.set_autocommit(True)
        with isolated.cursor() as cursor:
            cursor.execute("SET lock_timeout = '2s'")
            cursor.execute("SET statement_timeout = '3s'")
            if release:
                cursor.execute('DELETE FROM notifications_smsdispatchfence WHERE delivery_id = %s', [str(identifier)])
                return True
            cursor.execute('INSERT INTO notifications_smsdispatchfence (delivery_id, created_at) VALUES (%s, %s) '
                           'ON CONFLICT DO NOTHING', [str(identifier), timezone.now()])
            return cursor.rowcount == 1
    except Exception:
        raise TerminalDeliveryError('sms_fence_unavailable') from None
    finally:
        isolated.close()


def verify_webhook(body, headers, keys, *, namespace='admincore-webhook', now=None):
    """接收端辅助：验签、五分钟窗口、原子去重。生产接收端必须使用共享缓存。

    返回 True 后接收端应持久化事件再返回 2xx；业务仍须以 id 做持久幂等。
    此辅助函数不是公网入站路由，也不提供短信状态回调。
    """
    if len(body) > 100000:
        return False
    try:
        key = keys[headers['X-AdminCore-Key-Id']]
        stamp = headers['X-AdminCore-Timestamp']
        identifier = str(UUID(headers['X-AdminCore-Event-Id']))
        if not re.fullmatch(r'[0-9]{1,12}', stamp) or abs((time.time() if now is None else now) - int(stamp)) > 300:
            return False
        expected = 'sha256=' + hmac.new(key.encode(), stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, headers['X-AdminCore-Signature']):
            return False
        if json.loads(body)['id'] != identifier:
            return False
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return cache.add(namespace + ':' + identifier, True, timeout=601)
