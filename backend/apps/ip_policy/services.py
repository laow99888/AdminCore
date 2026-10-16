"""每次请求读取最新策略；不跨请求缓存准入结果，数据库失败时拒绝。"""
import ipaddress
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from apps.auth_app.reauthentication import require_recent_password
from apps.core.client_ip import request_ip
from apps.core.modules import module_enabled
from apps.logs.audit import snapshot, write_audit
from apps.permissions.permissions import has_permission_code
from .models import IPPolicy


class PolicyUnavailable(APIException):
    status_code = 503
    default_detail = 'IP 访问策略暂不可用'


class PolicyConflict(APIException):
    status_code = 409
    default_detail = '记录已变化，请查看最新值后重试'


def permits(values, source):
    if not values['enabled']:
        return True
    try:
        address = ipaddress.ip_address(source)
        if '%' in source:
            return False
        # 对 IPv4-mapped IPv6 同时采用 IPv4 和 IPv6 规则；任一拒绝优先。
        addresses = [address]
        if address.version == 6 and address.ipv4_mapped:
            addresses.append(address.ipv4_mapped)
        allow = [ipaddress.ip_network(value) for value in values['allow']]
        deny = [ipaddress.ip_network(value) for value in values['deny']]
        matches = lambda networks: any(ip.version == net.version and ip in net for ip in addresses for net in networks)
        return not matches(deny) and (not allow or matches(allow))
    except (ValueError, TypeError, KeyError):
        return False


def current_policy():
    row = IPPolicy.objects.filter(pk=1).first()
    if row is None:
        raise PolicyUnavailable()
    return row


def enforce(request):
    if not module_enabled('ip_policy'):
        return
    try:
        row = current_policy()
        allowed = permits({'enabled': row.enabled, 'allow': row.allow, 'deny': row.deny}, request_ip(request))
    except PolicyUnavailable:
        raise
    except Exception:
        raise PolicyUnavailable() from None
    if not allowed:
        raise PermissionDenied('当前来源不允许访问')


@transaction.atomic
def update_policy(request, values):
    if not module_enabled('ip_policy'):
        raise NotFound()
    actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if actor is None:
        raise AuthenticationFailed('登录凭据已撤销')
    if actor.must_change_password or not has_permission_code(actor, 'ip_policy:update'):
        raise PermissionDenied('没有 IP 策略操作权限')
    require_recent_password(request, actor, 'ip_policy:update')
    row = IPPolicy.objects.select_for_update().filter(pk=1).first()
    if row is None:
        raise PolicyUnavailable()
    if row.version != values['version']:
        raise PolicyConflict()
    if not permits(values, request_ip(request)):
        raise ValidationError('策略会拒绝当前来源，请先保留当前管理员访问')
    before = snapshot('ip_policy', row)
    for field in ('enabled', 'allow', 'deny'):
        setattr(row, field, values[field])
    row.version += 1
    row.save()
    write_audit(request=request, actor=actor, resource='ip_policy', identifier=1,
                before=before, after=snapshot('ip_policy', row))
    return row
