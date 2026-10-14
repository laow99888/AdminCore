"""宿主备份执行器：后台登记计划，宿主协调停写；不向应用暴露 Docker socket。

python scripts/backup_runner.py --once
python scripts/backup_runner.py --backup-dir /mnt/independent/admincore
失败保留 partial/诊断文件；只回收本执行器发布且重新校验通过的完整备份。
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
WRITERS = ('frontend', 'worker', 'beat', 'backend')
STAMP = re.compile(r'\d{8}-\d{6}')


class RunnerError(Exception):
    pass


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def artifact(path):
    return {'name': path.name, 'sha256': digest(path), 'bytes': path.stat().st_size}


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.partial')
    with temporary.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=False, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def restore_command(stamp):
    """Windows 显式使用 Git Bash，避免 PATH 上的 WSL bash 接收宿主路径。"""
    bash = os.getenv('ADMINCORE_BASH', '')
    if not bash and os.name == 'nt':
        candidate = Path(os.getenv('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe'
        if candidate.is_file():
            bash = str(candidate)
        else:
            raise RunnerError('Windows 恢复需安装 Git Bash 或配置 ADMINCORE_BASH；不使用 WSL bash')
    return [bash or shutil.which('bash') or 'bash', 'scripts/restore.sh', stamp]


@contextmanager
def runner_lock(folder):
    """操作系统文件锁；进程死亡自动释放，保留锁文件避免 inode 竞争。"""
    with (folder / '.runner.lock').open('a+b') as lock:
        lock.seek(0)
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RunnerError('已有备份执行器持有此目录锁') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def validated_set(folder, marker):
    """只信任固定文件名、无链接、摘要一致的执行器标记。"""
    if marker.is_symlink() or not marker.is_file():
        raise RunnerError('无效备份标记')
    data = json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise RunnerError('无效备份标记')
    stamp = data.get('timestamp', '')
    if data.get('version') != 1 or not isinstance(stamp, str) or not STAMP.fullmatch(stamp) or marker.name != f'admincore-{stamp}.backup.json':
        raise RunnerError('无效备份标记')
    expected = [f'admincore-db-{stamp}.dump', f'admincore-media-{stamp}.tar.gz', f'admincore-{stamp}.sha256']
    rows = data.get('artifacts', [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows) or [row.get('name') for row in rows] != expected:
        raise RunnerError('备份文件不完整')
    paths = [folder / name for name in expected]
    for path, row in zip(paths, rows):
        if path.is_symlink() or not path.is_file() or artifact(path) != row:
            raise RunnerError('备份校验失败')
    manifest = ''.join(f'{row["sha256"]}  {row["name"]}\n' for row in rows[:2])
    if paths[2].read_text(encoding='utf-8') != manifest:
        raise RunnerError('备份清单不匹配')
    return data, paths


def prune(folder, days, count, now=None):
    """同时满足超龄和超出最少份数才清理；损坏/人工备份永不删除。"""
    now = now or datetime.now(timezone.utc)
    complete, warning = [], False
    for marker in folder.glob('admincore-*.backup.json'):
        try:
            data, paths = validated_set(folder, marker)
            if data.get('record_id') == 'manual':
                continue
            created = datetime.fromisoformat(data['created_at'])
            if created.tzinfo is None:
                raise ValueError('missing timezone')
            complete.append((created, marker, paths))
        except (RunnerError, ValueError, KeyError, TypeError, OSError):
            warning = True
    complete.sort(key=lambda row: row[0], reverse=True)
    deleted = 0
    for created, marker, paths in complete[count:]:
        if created >= now - timedelta(days=days):
            continue
        try:
            # 删除前再次验证，拒绝被替换为链接/未知数据；先移除完成标记。
            validated_set(folder, marker)
            marker.unlink()
            for path in paths:
                path.unlink()
            deleted += 1
        except (RunnerError, OSError, ValueError):
            warning = True
    return deleted, warning


class Runner:
    def __init__(self, folder, compose=None):
        self.folder = Path(folder).absolute()
        # 可由隔离验收显式注入 Compose 项目，产品 CLI 只操作当前工作区。
        self.compose = compose or ['docker', 'compose']
        self.folder.mkdir(parents=True, exist_ok=True)
        if self.folder.is_symlink() or self.folder.resolve() != self.folder:
            raise RunnerError('备份目录不能经过符号链接')
        for restricted in ('backend', 'frontend', 'media', 'logs', '.git'):
            if self.folder.is_relative_to(ROOT / restricted):
                raise RunnerError('备份目录不能位于应用或媒体目录')

    def command(self, args, *, output=None, source=None, payload=None, timeout=300):
        deadline = getattr(self, '_deadline', None)
        if deadline is not None:
            timeout = min(timeout, max(1, deadline - time.monotonic()))
        result = subprocess.run(self.compose + args, cwd=ROOT, stdout=output or subprocess.PIPE,
                                stderr=subprocess.PIPE, stdin=source, input=payload, timeout=timeout)
        if result.returncode:
            # 不记录 Docker stderr，避免环境/存储凭据被异常文本泄露。
            raise RunnerError('白名单容器操作失败')
        return result.stdout

    def queue(self, action, *args, payload=None):
        raw = self.command(['exec', '-T', 'backend', 'python', 'manage.py', 'backup_queue', action, *args],
                           payload=json.dumps(payload).encode() if payload is not None else None)
        return json.loads(raw)

    def snapshot(self, request):
        self.stage = 'prepare'
        deadline = time.monotonic() + 90 * 60
        self._deadline = deadline
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        db = self.folder / f'admincore-db-{stamp}.dump'
        media = self.folder / f'admincore-media-{stamp}.tar.gz'
        manifest = self.folder / f'admincore-{stamp}.sha256'
        marker = self.folder / f'admincore-{stamp}.backup.json'
        if any(path.exists() for path in (db, media, manifest, marker, db.with_name(db.name + '.partial'), media.with_name(media.name + '.partial'))):
            raise RunnerError('备份时间戳冲突，拒绝覆盖')
        running = self.command(['ps', '--status', 'running', '--services']).decode().split()
        if not {'db', 'redis', 'backend'} <= set(running):
            raise RunnerError('基础服务未运行')
        writers = [service for service in WRITERS if service in running]
        resume_error = False
        try:
            self.stage = 'stop_writers'
            self.command(['stop', '-t', '120', *writers], timeout=180)
            self.stage = 'database_dump'
            with db.with_name(db.name + '.partial').open('xb') as output:
                self.command(['exec', '-T', 'db', 'sh', '-c', 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
                             output=output, timeout=3600)
            self.stage = 'media_export'
            with media.with_name(media.name + '.partial').open('xb') as output:
                self.command(['run', '--rm', '--no-deps', '-T', '--entrypoint', 'python', 'backend', '/app/docker/media_backup.py'],
                             output=output, timeout=3600)
            # 停写窗口只做快照；传输/清理在服务恢复后进行。
            db.with_name(db.name + '.partial').replace(db)
            media.with_name(media.name + '.partial').replace(media)
        finally:
            # 即便快照达到预算，也须给服务恢复留出独立时间。
            self._deadline = None
            try:
                self.command(['start', *writers], timeout=180)
                self.command(['up', '-d', '--no-deps', '--no-recreate', '--wait', '--wait-timeout', '150', *writers], timeout=180)
            except (RunnerError, subprocess.TimeoutExpired):
                resume_error = True
            if resume_error:
                raise RunnerError('service_resume_failed')
        rows = [artifact(db), artifact(media)]
        self._deadline = deadline
        self.stage = 'verify_archive'
        with db.open('rb') as source:
            self.command(['exec', '-T', 'db', 'pg_restore', '--list'], source=source)
        with tarfile.open(media, 'r|gz') as archive:
            for member in archive:
                parts = member.name.split('/')
                if (not member.isfile() or parts[0] != 'media' or len(parts) < 2
                        or any(part in ('', '.', '..') for part in parts) or '\\' in member.name
                        or ':' in member.name or any(ord(char) < 32 for char in member.name)):
                    raise RunnerError('媒体归档包含不安全条目')
                with archive.extractfile(member) as source:
                    for _ in iter(lambda: source.read(1024 * 1024), b''):
                        pass
        with manifest.with_name(manifest.name + '.partial').open('x', encoding='utf-8', newline='\n') as output:
            output.write(''.join(f'{row["sha256"]}  {row["name"]}\n' for row in rows))
        manifest.with_name(manifest.name + '.partial').replace(manifest)
        rows.append(artifact(manifest))
        remote = []
        self.stage = 'remote_copy'
        for path, row in zip((db, media, manifest), rows):
            with path.open('rb') as source:
                raw = self.command(['run', '--rm', '--no-deps', '-T', '--entrypoint', 'python', 'backend',
                                    '/app/docker/backup_upload.py', stamp, row['name'], row['sha256'], str(row['bytes'])],
                                   source=source, timeout=3600)
            remote.append(json.loads(raw)['remote_copy'])
        if len(set(remote)) != 1:
            raise RunnerError('备份副本配置在执行中变化')
        atomic_json(marker, {'version': 1, 'timestamp': stamp, 'record_id': request['record_id'],
                             'created_at': datetime.now(timezone.utc).isoformat(), 'artifacts': rows, 'remote_copy': remote[0]})
        self.stage = 'retention'
        pruned, warning = prune(self.folder, request['retention_days'], request['retention_count'])
        return {'timestamp': stamp, 'artifacts': rows, 'remote_copy': remote[0],
                'pruned_sets': pruned, 'retention_warning': warning}

    def once(self):
        request = self.queue('claim')
        if request is None:
            return False
        identifier, token = request['record_id'], request['token']
        try:
            result = self.snapshot(request)
            atomic_json(self.folder / f'admincore-{identifier}.receipt.json', result)
        except Exception as exc:
            self._deadline = None
            code = 'service_resume_failed' if str(exc) == 'service_resume_failed' else 'backup_failed'
            atomic_json(self.folder / f'admincore-{identifier}.failure.json',
                        {'code': code, 'stage': getattr(self, 'stage', 'unknown'), 'error_type': type(exc).__name__})
            try:
                self.queue('fail', identifier, '--token', token, '--code', code)
            except Exception:
                print('失败记录未回写；后台租约到期将标记结果未知。', flush=True)
            raise RunnerError(code) from None
        self._deadline = None
        # 产物已完整发布，但回写失败时不误报备份失败，也不重放停写。
        try:
            self.queue('finish', identifier, '--token', token, payload=result)
        except Exception:
            raise RunnerError('备份已发布，结果回写失败；保留 receipt，须人工核对，不自动重放') from None
        print(f'备份完成：{result["timestamp"]}，独立副本：{result["remote_copy"]}，清理旧备份：{result["pruned_sets"]}', flush=True)
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir', default=os.getenv('BACKUP_DIR', str(ROOT / 'backups')))
    parser.add_argument('--once', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--manual', action='store_true', help='人工停写备份，不登记后台任务')
    mode.add_argument('--restore', metavar='YYYYMMDD-HHMMSS', help='持有统一锁后调用交互恢复脚本')
    parser.add_argument('--poll-seconds', type=int, default=30)
    args = parser.parse_args()
    if not 10 <= args.poll_seconds <= 300:
        parser.error('轮询间隔必须为 10–300 秒')
    runner = Runner(args.backup_dir)
    coordinator = ROOT / '.codex-validation' / 'backup-coordinator'
    coordinator.mkdir(parents=True, exist_ok=True)
    if args.restore and not STAMP.fullmatch(args.restore):
        parser.error('恢复时间戳格式无效')
    if args.manual or args.restore:
        with runner_lock(coordinator), runner_lock(runner.folder):
            if args.restore:
                return subprocess.call(restore_command(args.restore), cwd=ROOT,
                                       env={**os.environ, 'BACKUP_DIR': runner.folder.as_posix(), 'ADMINCORE_BACKUP_COORDINATED': '1'})
            result = runner.snapshot({'record_id': 'manual', 'retention_days': 3650, 'retention_count': 1000})
            print(f'备份完成：{result["timestamp"]}，目录：{runner.folder}；恢复：bash scripts/restore.sh {result["timestamp"]}')
            return 0
    while True:
        try:
            with runner_lock(coordinator), runner_lock(runner.folder):
                runner.once()
        except (RunnerError, subprocess.TimeoutExpired) as exc:
            print(str(exc) if isinstance(exc, RunnerError) else '容器操作超时；保留现场。', flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == '__main__':
    raise SystemExit(main())
