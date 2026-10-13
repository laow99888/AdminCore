"""媒体归档和对象存储切换；只操作部署配置指定的媒体命名空间。"""
import hashlib
import json
import tarfile
from pathlib import Path
from tempfile import SpooledTemporaryFile

from django.core.files import File
from django.core.files.storage import FileSystemStorage

RESTORE_PREFIX = '.admincore-restore-'


def safe_key(key):
    parts = key.split('/')
    if (not key or key.startswith('/') or '\\' in key or ':' in key
            or any(part in ('', '.', '..') for part in parts)
            or any(ord(char) < 32 for char in key)):
        raise ValueError('存储返回了不安全的媒体键')
    return key


def media_keys(storage, directory=''):
    """仅列举活动媒体，恢复副本保留在独立的隐藏前缀内。"""
    directories, files = storage.listdir(directory)
    for name in sorted(directories):
        if name.startswith(RESTORE_PREFIX):
            continue
        if '/' in name or '\\' in name:
            raise ValueError('存储返回了不安全的目录名')
        key = safe_key(f'{directory}/{name}' if directory else name)
        # 本地归档不能跟随链接读取媒体目录以外的数据。
        if isinstance(storage, FileSystemStorage) and Path(storage.path(key)).is_symlink():
            raise ValueError('媒体归档不支持符号链接')
        yield from media_keys(storage, key)
    for name in sorted(files):
        if name.startswith(RESTORE_PREFIX):
            continue
        if '/' in name or '\\' in name:
            raise ValueError('存储返回了不安全的文件名')
        key = safe_key(f'{directory}/{name}' if directory else name)
        if isinstance(storage, FileSystemStorage) and Path(storage.path(key)).is_symlink():
            raise ValueError('媒体归档不支持符号链接')
        yield key


def export_media(storage, output):
    with tarfile.open(fileobj=output, mode='w|gz') as archive:
        for key in media_keys(storage):
            member = tarfile.TarInfo(f'media/{key}')
            member.size = storage.size(key)
            member.mode = 0o600
            with storage.open(key, 'rb') as source:
                archive.addfile(member, source)


def digest(storage, key):
    result = hashlib.sha256()
    with storage.open(key, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def copy_exact(source_storage, source_key, destination, destination_key):
    """副本验证成功后才允许后续删除；不接受存储后端悄悄改名。"""
    safe_key(source_key)
    safe_key(destination_key)
    if destination.exists(destination_key):
        raise ValueError('目标媒体键已存在，拒绝覆盖')
    checksum = hashlib.sha256()
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as temporary:
        with source_storage.open(source_key, 'rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                checksum.update(chunk)
                temporary.write(chunk)
        temporary.seek(0)
        saved = destination.save(destination_key, File(temporary))
    if saved != destination_key:
        raise ValueError('存储后端改变了媒体键，已中止切换')
    if digest(destination, destination_key) != checksum.hexdigest():
        raise ValueError('媒体副本校验失败，已中止切换')
    return checksum.hexdigest()


def save_state(stage, state):
    temporary = stage / 'state.tmp'
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.replace(stage / 'state.json')


def storage_identity(storage):
    return {'bucket': storage.bucket_name, 'location': storage.location,
            'endpoint': storage.endpoint_url, 'region': storage.region_name}


def restore_objects(storage, stage, action):
    """先备份并验证每个旧对象再删除；日志使失败切换可重复回滚。"""
    state = json.loads((stage / 'state.json').read_text(encoding='utf-8'))
    if state.get('storage') != storage_identity(storage):
        raise ValueError('恢复期间存储配置已改变，拒绝操作其他命名空间')
    old_prefix = stage.name + '/old/'
    if action == 'commit':
        if state['phase'] != 'prepared':
            raise ValueError('归档未就绪或已切换')
        state['phase'] = 'committing'
        state['old_checksums'] = {}
        save_state(stage, state)
        for key in list(media_keys(storage)):
            checksum = copy_exact(storage, key, storage, old_prefix + key)
            state['old'].append(key)
            state['old_checksums'][key] = checksum
            save_state(stage, state)
            storage.delete(key)
        incoming = FileSystemStorage(location=stage / 'new' / 'media')
        for key in media_keys(incoming):
            state['new'].append(key)
            save_state(stage, state)
            copy_exact(incoming, key, storage, key)
        state['phase'] = 'committed'
        save_state(stage, state)
        return
    if action == 'rollback':
        if state['phase'] in ('prepared', 'rolled_back'):
            return
        # 回滚开始前验证全部旧副本，不能发现缺失/损坏后才停止删除当前文件。
        for key in state['old']:
            backup_key = old_prefix + safe_key(key)
            expected = state.get('old_checksums', {}).get(key)
            if not expected or not storage.exists(backup_key) or digest(storage, backup_key) != expected:
                raise ValueError('旧媒体副本缺失或校验失败，停止回滚')
        for key in state['new']:
            storage.delete(safe_key(key))
        for key in state['old']:
            backup_key = old_prefix + safe_key(key)
            storage.delete(key)
            copy_exact(storage, backup_key, storage, key)
        state['phase'] = 'rolled_back'
        save_state(stage, state)
        return
    raise ValueError('未知操作')
