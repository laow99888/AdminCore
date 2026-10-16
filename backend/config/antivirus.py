"""部署级 ClamAV 配置；不接受客户端地址，不执行命令或解析 DNS。"""
from dataclasses import dataclass
import ipaddress
import os
import socket

from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class AntivirusConfig:
    enabled: bool = False
    address: str = '127.0.0.1'
    port: int = 3310
    unix_socket: str = ''
    timeout: int = 20
    max_bytes: int = 50 * 1024 * 1024


def load_antivirus(environment):
    try:
        enabled = environment.get('ADMINCORE_ANTIVIRUS_ENABLED', 'False').lower()
        if enabled not in ('true', 'false'):
            raise ValueError()
        address = environment.get('ADMINCORE_CLAMAV_ADDRESS', '127.0.0.1')
        # 仅允许固定 Compose 服务名或数字私网地址；不接受任意域名，避免把扫描连接变成 SSRF 入口。
        if address != 'clamav':
            ip = ipaddress.ip_address(address)
            if ip.is_global or ip.is_unspecified or ip.is_multicast or ip.is_link_local:
                raise ValueError()
        port = int(environment.get('ADMINCORE_CLAMAV_PORT', '3310'))
        timeout = int(environment.get('ADMINCORE_CLAMAV_TIMEOUT', '20'))
        max_bytes = int(environment.get('ADMINCORE_CLAMAV_MAX_BYTES', str(50 * 1024 * 1024)))
        unix = environment.get('ADMINCORE_CLAMAV_SOCKET', '')
        if not (1 <= port <= 65535 and 1 <= timeout <= 60 and 1 <= max_bytes <= 500 * 1024 * 1024):
            raise ValueError()
        if unix and (not unix.startswith('/') or len(unix.encode('utf-8')) > 100 or '\x00' in unix
                     or '..' in unix.split('/') or not hasattr(socket, 'AF_UNIX') or os.name == 'nt'):
            raise ValueError()
        return AntivirusConfig(enabled == 'true', address, port, unix, timeout, max_bytes)
    except (ValueError, TypeError, AttributeError):
        raise ImproperlyConfigured('ClamAV 配置无效：仅支持 Compose 服务名 clamav、私网数字 IP 或 Unix socket，以及有界端口/超时/大小') from None
