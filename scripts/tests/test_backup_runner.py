"""宿主执行器安全边界：原子发布、故障恢复、限定回收、独立副本。"""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('backup_runner', ROOT / 'scripts/backup_runner.py')
upload = load('backup_upload', ROOT / 'backend/docker/backup_upload.py')


def make_set(folder, stamp, age):
    db = folder / f'admincore-db-{stamp}.dump'
    media = folder / f'admincore-media-{stamp}.tar.gz'
    manifest = folder / f'admincore-{stamp}.sha256'
    db.write_bytes(b'database')
    media.write_bytes(b'media')
    rows = [runner.artifact(db), runner.artifact(media)]
    manifest.write_text(''.join(f'{row["sha256"]}  {row["name"]}\n' for row in rows), encoding='utf-8')
    rows.append(runner.artifact(manifest))
    marker = folder / f'admincore-{stamp}.backup.json'
    runner.atomic_json(marker, {'version': 1, 'timestamp': stamp,
                              'created_at': (datetime.now(timezone.utc) - timedelta(days=age)).isoformat(),
                              'artifacts': rows})
    return db, media, manifest, marker


def test_retention_keeps_minimum_recent_manual_and_partial(tmp_path):
    latest = make_set(tmp_path, '20261014-010000', 40)
    expired = make_set(tmp_path, '20260901-010000', 43)
    recent = make_set(tmp_path, '20261013-010000', 1)
    manual = tmp_path / 'admincore-20200101-010000.sha256'
    manual.write_text('manual backup')
    partial = tmp_path / 'admincore-db-20200101-010000.dump.partial'
    partial.write_bytes(b'partial')
    assert runner.prune(tmp_path, 30, 2) == (1, False)
    assert all(path.exists() for path in latest + recent)
    assert all(not path.exists() for path in expired)
    assert manual.exists() and partial.exists()


def test_corruption_and_manifest_path_injection_are_never_deleted(tmp_path):
    corrupt = make_set(tmp_path, '20200101-010000', 100)
    corrupt[0].write_bytes(b'tampered')
    unsafe = make_set(tmp_path, '20200102-010000', 100)
    data = json.loads(unsafe[3].read_text())
    data['artifacts'][0]['name'] = '../../private'
    unsafe[3].write_text(json.dumps(data))
    assert runner.prune(tmp_path, 1, 0) == (0, True)
    assert all(path.exists() for path in corrupt + unsafe)


class FakeRunner(runner.Runner):
    def __init__(self, folder, failed=False):
        super().__init__(folder)
        self.operations = []
        self.failed = failed

    def command(self, args, **kwargs):
        self.operations.append(args)
        if args[0] == 'ps':
            return b'db\nredis\nbackend\nfrontend\nworker\nbeat\n'
        if kwargs.get('output'):
            if self.failed and args[0] == 'run':
                raise runner.RunnerError('media failed')
            if args[0] == 'run':
                with tarfile.open(fileobj=kwargs['output'], mode='w:gz') as archive:
                    member = tarfile.TarInfo('media/fixture.txt')
                    member.size = 7
                    archive.addfile(member, io.BytesIO(b'fixture'))
            else:
                kwargs['output'].write(b'fixture snapshot')
        if '/app/docker/backup_upload.py' in args:
            return b'{"remote_copy":false}'
        return b''


def test_success_publishes_verified_portable_set_after_resume(tmp_path):
    instance = FakeRunner(tmp_path)
    result = instance.snapshot({'record_id': 'fixture', 'retention_days': 30, 'retention_count': 7})
    marker = tmp_path / f'admincore-{result["timestamp"]}.backup.json'
    data, paths = runner.validated_set(tmp_path, marker)
    assert data['artifacts'] == result['artifacts'] and len(paths) == 3
    start = next(i for i, row in enumerate(instance.operations) if row[0] == 'start')
    transfer = next(i for i, row in enumerate(instance.operations) if '/app/docker/backup_upload.py' in row)
    assert start < transfer and not list(tmp_path.glob('*.partial'))


def test_minimal_backup_does_not_require_optional_redis(tmp_path):
    class MinimalRunner(FakeRunner):
        def command(self, args, **kwargs):
            if args[0] == 'ps':
                return b'db\nbackend\nfrontend\n'
            return super().command(args, **kwargs)
    instance = MinimalRunner(tmp_path)
    result = instance.snapshot({'record_id': 'manual', 'retention_days': 30, 'retention_count': 7})
    assert result['artifacts']
    stop = next(row for row in instance.operations if row[0] == 'stop')
    assert 'redis' not in stop and 'worker' not in stop


def test_failure_always_resumes_original_writers_and_keeps_partial(tmp_path):
    instance = FakeRunner(tmp_path, failed=True)
    with pytest.raises(runner.RunnerError):
        instance.snapshot({'record_id': 'fixture', 'retention_days': 30, 'retention_count': 7})
    assert ['start', 'frontend', 'worker', 'beat', 'backend'] in instance.operations
    assert len(list(tmp_path.glob('*.partial'))) == 2
    assert not list(tmp_path.glob('*.backup.json'))


@pytest.mark.parametrize('failed', [False, True])
def test_snapshot_stops_and_resumes_running_realtime_role(tmp_path, failed):
    class RealtimeRunner(FakeRunner):
        def command(self, args, **kwargs):
            if args[0] == 'ps':
                return b'db\nredis\nbackend\nfrontend\nworker\nbeat\nrealtime\n'
            return super().command(args, **kwargs)
    host = RealtimeRunner(tmp_path, failed=failed)
    if failed:
        with pytest.raises(runner.RunnerError):
            host.snapshot({'record_id': 'fixture', 'retention_days': 30, 'retention_count': 7})
    else:
        host.snapshot({'record_id': 'fixture', 'retention_days': 30, 'retention_count': 7})
    for operation in ('stop', 'start', 'up'):
        calls = [args for args in host.operations if args[0] == operation]
        assert len(calls) == 1 and 'realtime' in calls[0]


@pytest.mark.skipif(runner.os.name == 'nt', reason='POSIX Bash contract runs in Linux')
@pytest.mark.parametrize('failed', [False, True])
def test_restore_coordinates_only_original_running_roles_including_realtime(tmp_path, failed):
    import os
    import shutil
    import subprocess
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copyfile(ROOT / 'scripts/restore.sh', scripts / 'restore.sh')
    (scripts / 'health_check.sh').write_text('#!/bin/sh\nexit 0\n')
    backups = tmp_path / 'backups'
    backups.mkdir()
    stamp = '20261017-010000'
    paths = [backups / f'admincore-db-{stamp}.dump', backups / f'admincore-media-{stamp}.tar.gz']
    for path in paths:
        path.write_bytes(b'only role coordination is tested; no database or Docker daemon')
    (backups / f'admincore-{stamp}.sha256').write_text(''.join(f'{runner.digest(path)}  {path.name}\n' for path in paths))
    binary = tmp_path / 'bin'
    binary.mkdir()
    docker = binary / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['ROLE_COMMAND_LOG'], 'a') as output:
    output.write(json.dumps(args) + '\\n')
if args[:2] == ['compose', 'ps']:
    print('db\\nredis\\nbackend\\nfrontend\\nrealtime')
if os.environ['ROLE_FAIL_COMMIT'] == '1' and 'commit' in args:
    raise SystemExit(1)
''')
    docker.chmod(0o700)
    log = tmp_path / 'commands.jsonl'
    result = subprocess.run(['bash', str(scripts / 'restore.sh'), stamp], cwd=tmp_path,
        env={**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
             'BACKUP_DIR': str(backups), 'ADMINCORE_BACKUP_COORDINATED': '1',
             'ADMINCORE_RESTORE_CONFIRMED': '1', 'ROLE_COMMAND_LOG': str(log),
             'ROLE_FAIL_COMMIT': str(int(failed))}, capture_output=True, text=True, timeout=20)
    assert result.returncode == (1 if failed else 0), result.stdout + result.stderr
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    for action in ('stop', 'start'):
        calls = [args for args in commands if args[:2] == ['compose', action]]
        assert calls and all(set(args[2:]) == {'frontend', 'backend', 'realtime'} for args in calls)


def test_result_writeback_failure_does_not_repeat_or_mark_snapshot_failed(tmp_path):
    instance = FakeRunner(tmp_path)
    calls = []
    def queue(action, *args, **kwargs):
        calls.append(action)
        if action == 'claim-restore':
            return None
        if action == 'claim':
            return {'record_id': 'fixture', 'token': 'claim', 'retention_days': 30, 'retention_count': 7}
        raise runner.RunnerError('unavailable')
    instance.queue = queue
    with pytest.raises(runner.RunnerError, match='回写失败'):
        instance.once()
    assert calls == ['heartbeat', 'claim-restore', 'claim', 'finish']
    assert (tmp_path / 'admincore-fixture.receipt.json').exists()
    assert len(list(tmp_path.glob('*.backup.json'))) == 1


def test_runner_directory_lock_excludes_second_process(tmp_path):
    with runner.runner_lock(tmp_path):
        with pytest.raises(runner.RunnerError):
            with runner.runner_lock(tmp_path):
                pass


def test_upload_disabled_does_not_require_media_s3_credentials(monkeypatch):
    monkeypatch.delenv('ADMINCORE_BACKUP_S3_BUCKET', raising=False)
    assert upload.upload('20261014-010000', 'x', 'x', 0, io.BytesIO()) == {'remote_copy': False}


@pytest.mark.parametrize('prefix,endpoint', [('../escape', ''), ('valid', 'http://private'),
                                          ('valid', 'https://user:secret@private'), ('valid', 'https://private/path')])
def test_remote_rejects_unsafe_configuration(monkeypatch, prefix, endpoint):
    monkeypatch.setenv('ADMINCORE_BACKUP_S3_BUCKET', 'private-fixture')
    monkeypatch.setenv('ADMINCORE_BACKUP_S3_PREFIX', prefix)
    monkeypatch.setenv('ADMINCORE_BACKUP_S3_ENDPOINT', endpoint)
    monkeypatch.delenv('ADMINCORE_BACKUP_S3_ALLOW_HTTP', raising=False)
    with pytest.raises(ValueError):
        upload.upload('20261014-010000', 'admincore-db-20261014-010000.dump', hashlib.sha256(b'x').hexdigest(), 1, io.BytesIO(b'x'))


@pytest.mark.parametrize('corrupt', [False, True])
def test_remote_upload_requires_private_acl_and_readback_digest(monkeypatch, corrupt):
    import boto3
    from botocore.exceptions import ClientError
    for key, value in {'ADMINCORE_BACKUP_S3_BUCKET': 'private-fixture', 'ADMINCORE_BACKUP_S3_PREFIX': 'safe',
                       'ADMINCORE_BACKUP_S3_ENDPOINT': 'https://backup.example.test',
                       'ADMINCORE_BACKUP_S3_ACCESS_KEY': 'fixture-access', 'ADMINCORE_BACKUP_S3_SECRET_KEY': 'fixture-secret'}.items():
        monkeypatch.setenv(key, value)
    class Client:
        def head_object(self, **kwargs):
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')
        def upload_fileobj(self, source, bucket, key, ExtraArgs):
            assert bucket == 'private-fixture' and key.startswith('safe/')
            assert ExtraArgs['ACL'] == 'private'
            assert source.read() == b'x'
        def get_object(self, **kwargs):
            return {'Body': io.BytesIO(b'changed' if corrupt else b'x')}
    monkeypatch.setattr(boto3, 'client', lambda *args, **kwargs: Client())
    arguments = ('20261014-010000', 'admincore-db-20261014-010000.dump', hashlib.sha256(b'x').hexdigest(), 1, io.BytesIO(b'x'))
    if corrupt:
        with pytest.raises(ValueError, match='remote_backup_checksum_mismatch'):
            upload.upload(*arguments)
    else:
        assert upload.upload(*arguments) == {'remote_copy': True}


def test_retention_never_deletes_runner_manual_backup(tmp_path):
    files = make_set(tmp_path, '20200101-010000', 100)
    data = json.loads(files[3].read_text())
    data['record_id'] = 'manual'
    files[3].write_text(json.dumps(data))
    assert runner.prune(tmp_path, 1, 0) == (0, False)
    assert all(path.exists() for path in files)


@pytest.mark.parametrize('payload', [[], None, {'timestamp': 123},
                                   {'version': 1, 'timestamp': '20200101-010000', 'artifacts': [None]}])
def test_malformed_historical_markers_only_report_retention_warning(tmp_path, payload):
    marker = tmp_path / 'admincore-20200101-010000.backup.json'
    marker.write_text(json.dumps(payload))
    assert runner.prune(tmp_path, 1, 0) == (0, True)
    assert marker.exists()


def test_windows_restore_selects_git_bash_and_forward_slash_path(tmp_path):
    if runner.os.name != 'nt':
        pytest.skip('Windows path contract')
    import subprocess
    command = runner.restore_command('20261014-010000')
    assert 'Git' in command[0] and command[1:] == ['scripts/restore.sh', '20261014-010000']
    result = subprocess.run([command[0], '-c', '[ -d "$ADMINCORE_TEST_ROOT" ]'],
                            env={**runner.os.environ, 'ADMINCORE_TEST_ROOT': ROOT.as_posix()}, capture_output=True)
    assert result.returncode == 0
    archive = tmp_path / 'archive.dump'
    archive.write_bytes(bytes(range(256)) + b'\r\n\x00\xff')
    result = subprocess.run([command[0], '-c', 'sha256sum --text "$ADMINCORE_TEST_ARCHIVE"'],
                            env={**runner.os.environ, 'ADMINCORE_TEST_ARCHIVE': archive.as_posix()},
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.split('  ', 1)[0] == runner.digest(archive)


def test_private_outputs_refuse_overwrite_and_keep_original_bytes(tmp_path):
    target = tmp_path / 'private.dump'
    with runner.private_output(target) as stream:
        stream.write(b'original')
    with pytest.raises(FileExistsError):
        with runner.private_output(target):
            pass
    assert target.read_bytes() == b'original'


def test_catalog_caches_unchanged_files_but_rechecks_changed_or_restore(tmp_path, monkeypatch):
    files = make_set(tmp_path, '20261014-010000', 0)
    host = runner.Runner(tmp_path)
    original = runner.validated_set
    checks = []
    def validate(*args):
        checks.append(args)
        return original(*args)
    monkeypatch.setattr(runner, 'validated_set', validate)
    assert len(host.catalog()) == 1
    assert len(host.catalog()) == 1 and len(checks) == 1
    assert len(host.catalog(fresh=True)) == 1 and len(checks) == 2
    files[0].write_bytes(b'tampered-database')
    assert host.catalog() == [] and len(checks) == 3


@pytest.mark.parametrize('exit_code', [0, 1])
def test_restore_intent_durable_before_execution_and_never_replayed(tmp_path, monkeypatch, exit_code):
    import uuid
    make_set(tmp_path, '20261014-010000', 0)
    host = runner.Runner(tmp_path)
    item = host.catalog()[0]
    identifier = str(uuid.uuid4())
    request = {'request_id': identifier, 'timestamp': item['timestamp'],
        'artifact_digest': hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()}
    operations = []
    def queue(action, *args, **kwargs):
        operations.append(action)
        return request if action == 'claim-restore' else {'updated': True}
    monkeypatch.setattr(host, 'queue', queue)
    receipt = tmp_path / f'admincore-restore-{identifier}.receipt.json'
    def execute(*args, **kwargs):
        assert json.loads(receipt.read_text())['error'] == 'restore_started'
        return exit_code
    monkeypatch.setattr(runner.subprocess, 'call', execute)
    assert host.once() is (exit_code == 0)
    assert json.loads(receipt.read_text())['status'] == ('succeeded' if exit_code == 0 else 'failed')
    monkeypatch.setattr(runner.subprocess, 'call', lambda *args, **kwargs: pytest.fail('恢复被重放'))
    assert host.once() is False
    assert operations.count('finish-restore') == 2


@pytest.mark.skipif(runner.os.name == 'nt', reason='POSIX 权限由 Linux CI 验证，Windows 另需宿主 ACL')
def test_private_modes_ignore_permissive_umask_and_reject_broad_existing_folder(tmp_path):
    original = runner.os.umask(0o022)
    try:
        folder = tmp_path / 'private-backups'
        runner.private_directory(folder)
        with runner.private_output(folder / 'snapshot.dump') as stream:
            stream.write(b'synthetic')
        runner.atomic_json(folder / 'receipt.json', {'synthetic': True})
        assert folder.stat().st_mode & 0o777 == 0o700
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in folder.iterdir())
        broad = tmp_path / 'existing-broad'
        broad.mkdir(mode=0o755)
        with pytest.raises(runner.RunnerError, match='权限过宽'):
            runner.private_directory(broad)
        assert broad.stat().st_mode & 0o777 == 0o755
    finally:
        runner.os.umask(original)
