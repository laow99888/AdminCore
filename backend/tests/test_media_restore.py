"""媒体卷切换与不可信归档路径的回归测试。"""
import importlib.util
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('media_restore', Path(__file__).resolve().parents[1] / 'docker/media_restore.py')
media_restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media_restore)


def archive(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name, content in entries:
            member = tarfile.TarInfo(name)
            if content is None:
                member.type = tarfile.SYMTYPE
                member.linkname = '/etc/passwd'
                tar.addfile(member)
            else:
                member.size = len(content)
                tar.addfile(member, io.BytesIO(content))
    buffer.seek(0)
    return buffer


@pytest.mark.parametrize('name,content', [('../escape', b'bad'), ('/absolute', b'bad'),
    ('media/../escape', b'bad'), ('media/link', None), ('media/.admincore-restore-owned/state.json', b'bad'),
    ('media/file:stream', b'bad'), ('media/back\\slash', b'bad')])
def test_unsafe_archive_keeps_existing_media(monkeypatch, tmp_path, name, content):
    root = tmp_path / 'media'
    root.mkdir()
    (root / 'current.txt').write_bytes(b'current')
    monkeypatch.setattr(media_restore, 'MEDIA', root)
    monkeypatch.setattr(media_restore.sys, 'stdin', SimpleNamespace(buffer=archive([(name, content)])))
    with pytest.raises(ValueError):
        media_restore.main('prepare', '20261013-120000-123')
    assert (root / 'current.txt').read_bytes() == b'current'
    assert not (tmp_path / 'escape').exists()


def test_media_commit_and_rollback_preserve_mount_root(monkeypatch, tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    (root / 'current.txt').write_bytes(b'current')
    monkeypatch.setattr(media_restore, 'MEDIA', root)
    monkeypatch.setattr(media_restore.sys, 'stdin', SimpleNamespace(buffer=archive([('media/restored.txt', b'backup')])))
    token = '20261013-120000-123'
    media_restore.main('prepare', token)
    assert (root / 'current.txt').read_bytes() == b'current'
    media_restore.main('commit', token)
    assert root.is_dir() and (root / 'restored.txt').read_bytes() == b'backup'
    assert not (root / 'current.txt').exists()
    media_restore.main('rollback', token)
    media_restore.main('rollback', token)
    assert (root / 'current.txt').read_bytes() == b'current'
    assert not (root / 'restored.txt').exists()


def test_corrupt_media_archive_keeps_current_files(monkeypatch, tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    (root / 'current.txt').write_bytes(b'current')
    monkeypatch.setattr(media_restore, 'MEDIA', root)
    monkeypatch.setattr(media_restore.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'corrupt archive')))
    with pytest.raises(tarfile.ReadError):
        media_restore.main('prepare', '20261013-120000-123')
    assert (root / 'current.txt').read_bytes() == b'current'


def test_empty_valid_archive_can_restore_empty_media(monkeypatch, tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    (root / 'current.txt').write_bytes(b'current')
    monkeypatch.setattr(media_restore, 'MEDIA', root)
    monkeypatch.setattr(media_restore.sys, 'stdin', SimpleNamespace(buffer=archive([])))
    token = '20261013-120000-123'
    media_restore.main('prepare', token)
    media_restore.main('commit', token)
    assert root.is_dir() and not (root / 'current.txt').exists()
    media_restore.main('rollback', token)
    assert (root / 'current.txt').read_bytes() == b'current'
