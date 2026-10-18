"""独立项目的审阅、应用、验收推进与源码恢复；不操作数据库和环境文件。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import uuid

from create_project import (META, MAX_BYTES, REVISION, ProjectError, allowed_file, load_project,
                            local_digest, manifest, plan_digest, snapshot, upgrade_plan)

WORK = '.admincore-upgrade'
LOCK = '.admincore-upgrade.lock'


def json_write(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode(), 0o600)


def atomic_write(path, content, mode):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode & 0o777)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(root):
    lock = root / LOCK
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ProjectError('已有升级命令或遗留锁；确认原进程结束后再人工移除锁文件') from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def read_json(path):
    if path.is_symlink() or path.is_junction() or path.stat().st_size > MAX_BYTES:
        raise ProjectError('升级记录路径或大小无效')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise ProjectError('升级记录不是有效JSON') from exc


def workspace(root):
    path = root / WORK
    if path.is_symlink() or path.is_junction() or not path.is_dir():
        raise ProjectError('未找到安全的待验收升级目录')
    return path


def validate_names(names):
    # 项目可在 Windows/Linux 之间迁移；不能以大小写或文件/目录别名覆盖其他文件。
    seen = set()
    for name in sorted(names, key=str.casefold):
        if not allowed_file(name):
            raise ProjectError('升级不能包含环境、实例配置或私有文件')
        parts = name.split('/')
        if any(part.endswith((' ', '.')) or part.split('.')[0].upper() in
               {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))} for part in parts):
            raise ProjectError('升级包含不兼容Windows的路径')
        key = name.casefold()
        if key in seen or any('/'.join(key.split('/')[:i]) in seen for i in range(1, len(parts))):
            raise ProjectError('升级存在大小写或文件/目录路径冲突')
        seen.add(key)


def apply_upgrade(root, source, plan, *, keep_local=(), take_upstream=(), allow_delete=False):
    root = Path(root).resolve()
    if not isinstance(plan, dict) or not isinstance(plan.get('to_revision'), str) or not REVISION.fullmatch(plan['to_revision']):
        raise ProjectError('升级计划必须是包含明确目标SHA的JSON对象')
    with locked(root):
        if (root / WORK).exists() or (root / WORK).is_symlink():
            raise ProjectError('前次升级尚未验收或恢复')
        fresh = upgrade_plan(root, source, plan.get('to_revision', ''))
        if fresh != plan:
            raise ProjectError('升级计划已过期或被修改；重新生成并审阅')
        before = load_project(root)
        revision, version, files = snapshot(source, fresh['to_revision'])
        validate_names(set(before['files']) | set(files))
        keep, take = set(keep_local), set(take_upstream)
        rows = {row['path']: row for row in fresh['changes'] if row['upstream_changed']}
        if keep & take or not (keep | take) <= set(rows):
            raise ProjectError('冲突决策必须指向计划中的上游变更且不能重复')
        if any(row['current'] == 'unsafe_path' for row in fresh['changes']):
            raise ProjectError('存在不安全路径，拒绝整个升级')
        unresolved = [name for name, row in rows.items() if row['conflict'] and name not in keep | take]
        if unresolved:
            raise ProjectError('请先明确冲突决策：' + ', '.join(unresolved))
        selected = [row for name, row in rows.items() if name not in keep and row['current'] != row['after']]
        if not allow_delete and any(row['after'] is None for row in selected):
            raise ProjectError('计划包含源码删除，审阅后显式提供--allow-delete')
        after = {**before, 'source_revision': revision, 'base_version': version, 'files': manifest(files)}
        work = root / WORK
        work.mkdir(mode=0o700)
        records = []
        # 在写任何业务源码前完成全部备份；备份不包含.env、媒体或数据库。
        for index, row in enumerate(selected):
            path = root / row['path']
            backup = str(index)
            mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
            if row['current'] is not None:
                atomic_write(work / backup, path.read_bytes(), mode)
            records.append({**row, 'backup': backup, 'mode': mode})
        expected = {row['path']: row['current'] if row['path'] in keep else row['after']
                    for row in fresh['changes'] if row['upstream_changed']}
        state = {'id': uuid.uuid4().hex, 'status': 'prepared', 'before': before, 'after': after,
                 'records': records, 'expected': expected, 'decisions': {'keep': sorted(keep), 'take': sorted(take)},
                 'plan_id': fresh['plan_id']}
        json_write(work / 'state.json', state)
        try:
            for row in records:
                path = root / row['path']
                if local_digest(root, row['path']) != row['current']:
                    raise ProjectError('应用期间源码变化；备份和记录已保留')
                if row['after'] is None:
                    path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    content, mode = files[row['path']]
                    atomic_write(path, content, mode)
            state['status'] = 'applied'
            json_write(work / 'state.json', state)
        except Exception:
            # 保留明确可恢复的 prepared 日志，不猜测删除用户随后写入的内容。
            raise ProjectError('源码应用未完成；运行upgrade-restore恢复，备份已保留') from None
        return {'applied': len(records), 'kept': sorted(keep), 'pending_validation': True,
                'to_revision': revision}


def load_state(root):
    work = workspace(root)
    state = read_json(work / 'state.json')
    try:
        if (state['status'] not in ('prepared', 'applied', 'accepted', 'restored')
                or len(state['id']) != 32 or any(c not in '0123456789abcdef' for c in state['id'])):
            raise ValueError()
        validate_names(state['expected'])
        validate_names(row['path'] for row in state['records'])
        for index, row in enumerate(state['records']):
            if row['backup'] != str(index):
                raise ValueError()
            if row['current'] is not None and local_digest(work, row['backup']) != row['current']:
                raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectError('升级记录或备份无效；未修改源码') from exc
    return work, state


def archive(root, work, state):
    folder = root / '.codex-validation' / 'project-upgrades'
    # 不跟随被替换的日志目录，也不覆盖已有验收证据。
    for path in (root / '.codex-validation', folder):
        if path.is_symlink() or path.is_junction() or (path.exists() and not path.is_dir()):
            raise ProjectError('升级证据目录不安全；待验收目录已保留')
        path.mkdir(exist_ok=True)
    destination = folder / state['id']
    if destination.exists() or destination.is_symlink():
        raise ProjectError('升级证据归档已存在，拒绝覆盖')
    work.rename(destination)
    return str(destination.relative_to(root))


def verify_expected(root, state):
    if load_project(root) != state['before']:
        raise ProjectError('原基线元数据发生变化；拒绝推进')
    for name, digest in state['expected'].items():
        if local_digest(root, name) != digest:
            raise ProjectError('待验收源码已变化：' + name + '；请恢复后重新规划')


def accept_upgrade(root, checks):
    """checks 是操作者显式提供的 argv 数组；绝不执行模板/计划内的命令或 shell。"""
    root = Path(root).resolve()
    if (not isinstance(checks, list) or not checks or len(checks) > 32
            or any(not isinstance(command, list) or not command or len(command) > 100
                   or any(not isinstance(arg, str) or not arg or '\0' in arg for arg in command) for command in checks)):
        raise ProjectError('验收命令必须是1至32个非空argv数组')
    with locked(root):
        work, state = load_state(root)
        if state['status'] == 'accepted':
            if load_project(root) != state['after']:
                verify_expected(root, state)
                json_write(root / META, state['after'])
            return {'accepted': True, 'evidence': archive(root, work, state)}
        if state['status'] != 'applied':
            raise ProjectError('仅完整应用后的升级可以验收')
        verify_expected(root, state)
        with (work / 'validation.log').open('a', encoding='utf-8') as log:
            for command in checks:
                try:
                    result = subprocess.run(command, cwd=root, shell=False, stdout=log,
                                            stderr=subprocess.STDOUT, timeout=1200)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise ProjectError('验收命令无法完成；原基线及日志已保留') from exc
                if result.returncode:
                    raise ProjectError('验收未通过；原基线及日志已保留')
        verify_expected(root, state)
        # 同时登记成功验收命令与目标版本；源码备份留在忽略目录供审计。
        state.update(status='accepted', checks=checks)
        json_write(work / 'state.json', state)
        json_write(root / META, state['after'])
        return {'accepted': True, 'to_revision': state['after']['source_revision'],
                'evidence': archive(root, work, state)}


def restore_upgrade(root):
    """只恢复待验收升级涉及的源码；已验收或再次编辑的文件不会被覆盖。"""
    root = Path(root).resolve()
    with locked(root):
        work, state = load_state(root)
        if state['status'] == 'restored':
            return {'restored': True, 'evidence': archive(root, work, state)}
        if state['status'] not in ('prepared', 'applied') or load_project(root) != state['before']:
            raise ProjectError('基线已变化或升级已验收；不能自动恢复')
        for row in state['records']:
            if local_digest(root, row['path']) not in (row['current'], row['after']):
                raise ProjectError('升级后源码再次修改，拒绝覆盖：' + row['path'])
        for row in reversed(state['records']):
            path = root / row['path']
            if local_digest(root, row['path']) == row['current']:
                continue
            if row['current'] is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(path, (work / row['backup']).read_bytes(), row['mode'])
        state['status'] = 'restored'
        json_write(work / 'state.json', state)
        return {'restored': True, 'evidence': archive(root, work, state)}
