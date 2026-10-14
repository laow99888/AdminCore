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


def test_failure_always_resumes_original_writers_and_keeps_partial(tmp_path):
    instance = FakeRunner(tmp_path, failed=True)
    with pytest.raises(runner.RunnerError):
        instance.snapshot({'record_id': 'fixture', 'retention_days': 30, 'retention_count': 7})
    assert ['start', 'frontend', 'worker', 'beat', 'backend'] in instance.operations
    assert len(list(tmp_path.glob('*.partial'))) == 2
    assert not list(tmp_path.glob('*.backup.json'))


def test_result_writeback_failure_does_not_repeat_or_mark_snapshot_failed(tmp_path):
    instance = FakeRunner(tmp_path)
    calls = []
    def queue(action, *args, **kwargs):
        calls.append(action)
        if action == 'claim':
            return {'record_id': 'fixture', 'token': 'claim', 'retention_days': 30, 'retention_count': 7}
        raise runner.RunnerError('unavailable')
    instance.queue = queue
    with pytest.raises(runner.RunnerError, match='回写失败'):
        instance.once()
    assert calls == ['claim', 'finish']
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
