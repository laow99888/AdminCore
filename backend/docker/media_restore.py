"""验证并切换媒体归档；保留原文件以便恢复失败时回滚。"""
import json
import os
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath

MEDIA = Path('/app/media')


def object_storage():
    if os.environ.get('ADMINCORE_STORAGE_BACKEND', 'local') != 's3':
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.core.files.storage import default_storage
    return default_storage


def save_state(stage, state):
    temporary = stage / 'state.tmp'
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.replace(stage / 'state.json')


def main(action, token):
    if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9]+', token):
        raise ValueError('无效恢复标识')
    stage = MEDIA / ('.admincore-restore-' + token)
    storage = object_storage()
    if action == 'prepare':
        stage.mkdir(parents=True, exist_ok=False)
        with tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz') as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                if (path.is_absolute() or '..' in path.parts or not path.parts
                        or '\\' in member.name or ':' in member.name
                        or any(ord(char) < 32 for char in member.name)
                        or path.parts[0] != 'media' or not (member.isdir() or member.isfile())
                        or any(part.startswith('.admincore-restore-') for part in path.parts)):
                    raise ValueError('媒体归档包含不安全路径或非普通文件')
                archive.extract(member, path=stage / 'new', filter='data')
        (stage / 'new' / 'media').mkdir(parents=True, exist_ok=True)
        (stage / 'old').mkdir()
        state = {'phase': 'prepared', 'old': [], 'new': []}
        if storage is not None:
            from apps.core.media_storage import storage_identity
            state['storage'] = storage_identity(storage)
        save_state(stage, state)
        return
    state = json.loads((stage / 'state.json').read_text(encoding='utf-8'))
    if storage is not None:
        from apps.core.media_storage import restore_objects
        return restore_objects(storage, stage, action)
    if 'storage' in state:
        raise ValueError('恢复期间存储模式已改变，拒绝操作本地媒体')
    if action == 'commit':
        if state['phase'] != 'prepared':
            raise ValueError('归档未就绪或已切换')
        state['phase'] = 'committing'
        save_state(stage, state)
        for entry in list(MEDIA.iterdir()):
            if entry.name.startswith('.admincore-restore-'):
                continue
            state['old'].append(entry.name)
            save_state(stage, state)
            entry.rename(stage / 'old' / entry.name)
        for entry in list((stage / 'new' / 'media').iterdir()):
            state['new'].append(entry.name)
            save_state(stage, state)
            entry.rename(MEDIA / entry.name)
        state['phase'] = 'committed'
        save_state(stage, state)
        return
    if action == 'rollback':
        if state['phase'] in ('prepared', 'rolled_back'):
            return
        failed = stage / 'failed'
        failed.mkdir(exist_ok=True)
        for name in state['new']:
            entry = MEDIA / name
            if entry.exists():
                entry.rename(failed / name)
        for name in state['old']:
            entry = stage / 'old' / name
            if entry.exists():
                entry.rename(MEDIA / name)
        state['phase'] = 'rolled_back'
        save_state(stage, state)
        return
    raise ValueError('未知操作')


if __name__ == '__main__':
    main(*sys.argv[1:])
