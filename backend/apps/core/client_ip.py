"""只沿显式可信的直接代理链解析来源；无效转发头退回直接来源。"""
import ipaddress
import socket
import time
from functools import lru_cache
from django.conf import settings


@lru_cache(maxsize=8)
def _proxy_addresses(hosts, epoch):
    addresses = set()
    for host in hosts:
        try:
            for value in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
                addresses.add(ipaddress.ip_address(value[4][0]))
        except (OSError, ValueError):
            # 服务尚未创建或 DNS 故障时不信任转发头，后续重新解析。
            continue
    return frozenset(addresses)


def request_ip(request):
    try:
        direct = ipaddress.ip_address(request.META.get('REMOTE_ADDR', ''))
    except (ValueError, AttributeError):
        return None
    networks = settings.ADMINCORE_TRUSTED_PROXIES
    hosts = getattr(settings, 'ADMINCORE_TRUSTED_PROXY_HOSTS', ())
    addresses = _proxy_addresses(tuple(hosts), int(time.monotonic() // 30)) if hosts else ()
    def trusted(address):
        return address in addresses or any(address.version == network.version and address in network for network in networks)
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
