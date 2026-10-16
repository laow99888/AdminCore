"""只沿显式可信的直接代理链解析来源；无效转发头退回直接来源。"""
import ipaddress
from django.conf import settings


def request_ip(request):
    try:
        direct = ipaddress.ip_address(request.META.get('REMOTE_ADDR', ''))
    except (ValueError, AttributeError):
        return None
    networks = settings.ADMINCORE_TRUSTED_PROXIES
    def trusted(address):
        return any(address.version == network.version and address in network for network in networks)
    if not trusted(direct):
        return str(direct)
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if not forwarded or len(forwarded) > 2048:
        return str(direct)
    try:
        chain = [ipaddress.ip_address(part.strip()) for part in forwarded.split(',')]
    except ValueError:
        return str(direct)
    current = direct
    for address in reversed(chain):
        if not trusted(current):
            break
        current = address
    return str(current)
