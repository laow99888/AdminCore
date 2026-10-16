"""ClamD INSTREAM：有界读取、总期限、结果审计；失败从不降级放行。"""
from contextvars import ContextVar
import hashlib
import logging
import socket
import struct
import tempfile
import time

from django.conf import settings
from django.core.files import File
from django.db import transaction

from apps.core.exceptions import APIError

logger = logging.getLogger(__name__)
scan_context = ContextVar('admincore_antivirus_request', default=None)
CHUNK_BYTES = 64 * 1024
REPLY_BYTES = 4096


class ScanRejected(APIError):
    pass


class ProtocolError(Exception):
    pass


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError()
    return value


def connect(config, deadline):
    family = socket.AF_UNIX if config.unix_socket else socket.AF_INET6 if ':' in config.address else socket.AF_INET
    connection = socket.socket(family, socket.SOCK_STREAM)
    try:
        connection.settimeout(remaining(deadline))
        connection.connect(config.unix_socket or (config.address, config.port))
        return connection
    except BaseException:
        connection.close()
        raise


def send(connection, data, deadline):
    connection.settimeout(remaining(deadline))
    connection.sendall(data)


def reply(connection, deadline):
    output = bytearray()
    while len(output) <= REPLY_BYTES:
        connection.settimeout(remaining(deadline))
        chunk = connection.recv(min(512, REPLY_BYTES + 1 - len(output)))
        if not chunk:
            raise ProtocolError()
        output.extend(chunk)
        if b'\0' in chunk:
            if output[-1:] != b'\0' or b'\0' in output[:-1] or len(output) > REPLY_BYTES:
                raise ProtocolError()
            return bytes(output[:-1])
    raise ProtocolError()


def audit_result(result, identifier=''):
    # 控制台审计在数据库回滚/后台执行失败时仍保留结果，绝不输出内容、路径或 daemon 原始回复。
    logger.info('File scan completed', extra={'event': 'file.scan', 'scan_state': result['outcome'],
                'scan_sha256': result['sha256'], 'scan_bytes': result['bytes']})
    context = scan_context.get()
    if context is not None:
        context['results'].append((result, str(identifier)))
        if len(context['results']) > 16:
            raise ScanRejected('单次请求的文件扫描次数超出限制', status_code=429)
    else:
        # 后台任务沿用事务；失败回滚时控制台事件仍在，成功提交后写业务审计。
        from apps.logs.audit import write_audit
        transaction.on_commit(lambda: write_audit(resource='file_scan', identifier=identifier,
                              action='other', after=result, status=200 if result['outcome'] == 'clean' else 422))


def register_artifact(field_file):
    """登记本请求新写入的存储对象，审计失败时由中间件补偿删除。"""
    context = scan_context.get()
    if context is None:
        return
    name = getattr(field_file, 'name', '')
    storage = getattr(field_file, 'storage', None)
    if name and storage is not None:
        # 保存刚刚产生该对象的模型实例，审计失败时同时补偿数据库记录。
        # 只在上传/头像保存完成后登记，因此不会误删历史读取对象。
        context.setdefault('artifacts', []).append((storage, name, getattr(field_file, 'instance', None)))


def checked_copy(source, *, stage, identifier=''):
    """返回私有且可 seek 的已扫描副本；调用方只消费该副本并负责 close。"""
    config = settings.ADMINCORE_ANTIVIRUS
    if not config.enabled:
        return source
    output = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode='w+b')
    result = {'outcome': 'unavailable', 'sha256': '', 'bytes': 0, 'stage': stage,
              'engine': '', 'signature_sha256': ''}
    digest, complete = hashlib.sha256(), False
    origin_position = source.tell() if hasattr(source, 'tell') else None
    deadline = time.monotonic() + config.timeout
    try:
        source.seek(0)
        with connect(config, deadline) as connection:
            send(connection, b'zVERSION\0', deadline)
            version = reply(connection, deadline)
            engine = version.split(b'/', 1)[0]
            if not engine.startswith(b'ClamAV ') or len(engine) > 40 or not all(32 <= value < 127 for value in engine):
                raise ProtocolError()
            result['engine'] = engine.decode('ascii')
        with connect(config, deadline) as connection:
            send(connection, b'zINSTREAM\0', deadline)
            while True:
                remaining(deadline)
                chunk = source.read(min(CHUNK_BYTES, config.max_bytes + 1 - result['bytes']))
                if not chunk:
                    complete = True
                    break
                result['bytes'] += len(chunk)
                if result['bytes'] > config.max_bytes:
                    result['outcome'] = 'limit'
                    raise ScanRejected('文件超过病毒扫描大小限制', status_code=413)
                digest.update(chunk)
                output.write(chunk)
                send(connection, struct.pack('!I', len(chunk)) + chunk, deadline)
            send(connection, b'\0\0\0\0', deadline)
            scanned = reply(connection, deadline)
        if scanned == b'stream: OK':
            result['outcome'] = 'clean'
        elif scanned.startswith(b'stream: ') and scanned.endswith(b' FOUND'):
            result['outcome'] = 'infected'
            result['signature_sha256'] = hashlib.sha256(scanned[8:-6]).hexdigest()
            raise ScanRejected('检测到恶意文件，已阻止上传或读取', status_code=422)
        else:
            raise ProtocolError()
        remaining(deadline)
        output.seek(0)
        return output
    except ScanRejected:
        output.close()
        raise
    except (OSError, ProtocolError, ValueError):
        output.close()
        raise ScanRejected('病毒扫描服务不可用，文件未放行', status_code=503) from None
    finally:
        if origin_position is not None:
            try:
                source.seek(origin_position)
            except (OSError, ValueError):
                pass
        if complete:
            result['sha256'] = digest.hexdigest()
        try:
            audit_result(result, identifier)
        except BaseException:
            output.close()
            raise


def checked_upload(upload, *, stage):
    if not settings.ADMINCORE_ANTIVIRUS.enabled:
        return upload
    scanned = checked_copy(upload, stage=stage)
    result = File(scanned, name=upload.name)
    result.content_type = getattr(upload, 'content_type', '')
    result._md5 = getattr(upload, '_md5', '')
    return result
