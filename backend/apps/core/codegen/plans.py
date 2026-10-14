"""预览后用原文件摘要复核；只修改显式选中的生成文件。"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import tempfile
import uuid
import difflib
from contextlib import contextmanager
from .spec import GenerationError

PLAN_VERSION = 1


def digest(value):
    return hashlib.sha256(value).hexdigest()


def safe_target(root, relative):
    if (not isinstance(relative, str) or any(piece in ('', '.', '..') or piece.endswith((' ', '.'))
            for piece in relative.split('/'))):
        raise GenerationError('输出路径不合法')
    part = PurePosixPath(relative)
    if part.is_absolute() or '\\' in relative or ':' in relative or any(piece in ('', '.', '..') for piece in part.parts):
        raise GenerationError('输出路径不合法')
    target = root.joinpath(*part.parts)
    current = target
    while current != root:
        if linked(current):
            raise GenerationError('输出不能穿过符号链接')
        current = current.parent
    if not target.resolve().is_relative_to(root.resolve()):
        raise GenerationError('输出越过指定目录')
    if target.exists() and not target.is_file():
        raise GenerationError('输出目标不是普通文件')
    return target


def linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def checked_root(root):
    root = Path(root).absolute()
    if linked(root) or (root.exists() and not root.is_dir()):
        raise GenerationError('输出根目录必须为普通目录')
    return root


def preview_diff(root, files):
    root = checked_root(root)
    result = []
    for name, content in sorted(files.items()):
        target = safe_target(root, name)
        try:
            before = target.read_text(encoding='utf-8') if target.exists() else ''
        except UnicodeError as error:
            raise GenerationError('旧文件不是UTF-8文本：' + name) from error
        result.extend(difflib.unified_diff(before.splitlines(keepends=True), content.splitlines(keepends=True),
            fromfile='before/' + name, tofile='after/' + name))
    return ''.join(result)


def make_plan(root, definition, files):
    root = checked_root(root)
    entries = []
    for name, content in sorted(files.items()):
        target = safe_target(root, name)
        before = target.read_bytes() if target.exists() else None
        after = content.encode('utf-8')
        entries.append({'path': name, 'before_sha256': digest(before) if before is not None else None,
            'after_sha256': digest(after), 'state': 'same' if before == after else 'changed' if before is not None else 'new'})
    return {'plan_version': PLAN_VERSION, 'definition': definition, 'entries': entries}


@contextmanager
def write_lock(root):
    evidence_root = root / '.codex-validation'
    if linked(evidence_root):
        raise GenerationError('备份目录不能是符号链接或目录联接')
    evidence_root.mkdir(parents=True, exist_ok=True)
    lock = evidence_root / 'codegen.lock'
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise GenerationError('目标存在生成器锁，请核查原任务后再操作') from error
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            output.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def apply_plan(root, plan, definition, files, selected):
    root = checked_root(root)
    with write_lock(root):
        return _apply_plan(root, plan, definition, files, selected)


def _apply_plan(root, plan, definition, files, selected):
    """计划不能携带可执行代码；产物必须由当前渲染器从原定义重新生成。"""
    if not isinstance(plan, dict) or plan.get('plan_version') != PLAN_VERSION or plan.get('definition') != definition:
        raise GenerationError('计划版本或定义不一致，请重新预览')
    entries = plan.get('entries')
    if (not isinstance(entries, list) or any(not isinstance(entry, dict) or not isinstance(entry.get('path'), str)
            for entry in entries)):
        raise GenerationError('计划文件集合无效')
    expected = {entry['path']: entry for entry in entries}
    if set(expected) != set(files) or len(expected) != len(entries):
        raise GenerationError('计划文件集合已变化')
    selected = list(selected)
    if (not selected or any(not isinstance(name, str) for name in selected)
            or len(set(selected)) != len(selected) or set(selected) - set(files)):
        raise GenerationError('必须明确选择有效且不重复的文件')
    targets = {}
    for name in selected:
        entry = expected[name]
        target = safe_target(root, name)
        before = target.read_bytes() if target.exists() else None
        if entry.get('before_sha256') != (digest(before) if before is not None else None) or entry.get('after_sha256') != digest(files[name].encode('utf-8')):
            raise GenerationError('文件或生成结果已变化，请重新预览：' + name)
        targets[name] = (target, before)
    # 保留所有将覆盖的原文件，便于人工核查和恢复；目录属于生成目标。
    evidence_root = root / '.codex-validation'
    if linked(evidence_root):
        raise GenerationError('备份目录不能是符号链接')
    backup = evidence_root / ('codegen-' + uuid.uuid4().hex)
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'state': 'prepared', 'selected': selected, 'originals': [
        {'path': name, 'backup': f'{index}.original' if targets[name][1] is not None else None}
        for index, name in enumerate(selected)]}
    for index, name in enumerate(selected):
        if targets[name][1] is not None:
            (backup / f'{index}.original').write_bytes(targets[name][1])
    (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    written = []
    try:
        for index, name in enumerate(selected):
            target, before = targets[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            safe_target(root, name)
            # 创建路径时再次复核，拒绝后台编辑造成的覆盖。
            current = target.read_bytes() if target.exists() else None
            if current != before:
                raise GenerationError('写入前原文件已变化：' + name)
            descriptor, partial = tempfile.mkstemp(prefix='.codegen-', dir=target.parent)
            try:
                with os.fdopen(descriptor, 'wb') as output:
                    output.write(files[name].encode('utf-8'))
                    output.flush(); os.fsync(output.fileno())
                safe_target(root, name)
                if (target.read_bytes() if target.exists() else None) != before:
                    raise GenerationError('替换前原文件已变化：' + name)
                os.replace(partial, target)
            finally:
                Path(partial).unlink(missing_ok=True)
            written.append(name)
    except Exception:
        # 已写入的文件逐个恢复；恢复失败仍保留原件和列表，不能假称整体成功。
        (backup / 'failed.json').write_text(json.dumps({'written': written, 'selected': selected}, ensure_ascii=False, indent=2), encoding='utf-8')
        conflicts = []
        for name in reversed(written):
            target, before = targets[name]
            try:
                safe_target(root, name)
            except GenerationError:
                conflicts.append(name)
                continue
            if not target.exists() or linked(target) or target.read_bytes() != files[name].encode('utf-8'):
                conflicts.append(name)
                continue
            if before is None:
                target.unlink()
            else:
                target.write_bytes(before)
        if conflicts:
            (backup / 'rollback-conflicts.json').write_text(json.dumps(conflicts, ensure_ascii=False), encoding='utf-8')
            raise GenerationError('恢复期间检测到外部修改，请从备份人工核查')
        raise
    manifest['state'] = 'committed'
    (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'written': selected, 'backup': str(backup)}
