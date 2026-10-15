import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

SPEC = importlib.util.spec_from_file_location('office_runner_fixture', Path(__file__).parents[1] / 'office_preview_runner.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
IMAGE = 'admincore/office@sha256:' + 'c' * 64


def test_container_security_flags_and_single_source_mount(tmp_path):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'private source')
    args = runner.container_args('admincore-office-' + 'a' * 32, source, IMAGE)
    for flag, value in (('--network', 'none'), ('--user', '65532:65532'), ('--cap-drop', 'ALL'),
                        ('--memory', '768m'), ('--memory-swap', '768m'), ('--pids-limit', '96'),
                        ('--security-opt', 'no-new-privileges:true'), ('--log-driver', 'none')):
        assert args[args.index(flag) + 1] == value
    assert '--read-only' in args and args.count('--mount') == 1
    assert 'readonly' in args[args.index('--mount') + 1] and 'docker.sock' not in str(args)
    assert args[-3:] == [IMAGE, '/opt/admincore/convert.py', 'docx']
    with pytest.raises(ValueError):
        runner.container_args('foreign-service', source, IMAGE)
    with pytest.raises(ValueError):
        runner.container_args('admincore-office-' + 'a' * 32, source, 'office:latest')


@pytest.mark.parametrize('output', [b'%PDF-fake', b'x' * (runner.MAX_BYTES + 1), b'not-pdf'], ids=['valid', 'oversized', 'invalid'])
def test_container_is_removed_for_success_or_invalid_output(tmp_path, output):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'x')
    commands = []
    process = SimpleNamespace(stdout=io.BytesIO(output), wait=lambda **kwargs: 0, poll=lambda: 0)
    def command(args, **kwargs):
        commands.append(args)
    if output.startswith(b'%PDF-'):
        assert runner.convert(source, IMAGE, command=command, popen=lambda *a, **k: process) == output
    else:
        with pytest.raises(ValueError):
            runner.convert(source, IMAGE, command=command, popen=lambda *a, **k: process)
    converter = next(args[args.index('--name') + 1] for args in commands if 'create' in args and '--name' in args and not args[args.index('--name') + 1].endswith('-loader'))
    assert ['docker', 'rm', '--force', converter] in commands
    assert commands[-1] == ['docker', 'volume', 'rm', converter + '-input']
    assert commands[-2] == ['docker', 'rm', '--force', converter + '-loader']
    assert not any('type=bind' in value for args in commands for value in args)
    copy = next(args for args in commands if args[:2] == ['docker', 'cp'])
    assert copy[-1] == converter + '-loader:/input/source.docx'


def test_create_failure_also_cleans_only_owned_name(tmp_path):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'x')
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[:2] == ['docker', 'create']:
            raise RuntimeError('fixture')
    with pytest.raises(RuntimeError):
        runner.convert(source, IMAGE, command=command)
    assert calls[-2][:3] == ['docker', 'rm', '--force']
    assert calls[-2][-1].endswith('-loader')
    assert calls[-1][:3] == ['docker', 'volume', 'rm']


def test_unconfirmed_container_cleanup_retries_only_owned_name_then_stops(tmp_path):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'x')
    calls = []
    process = SimpleNamespace(stdout=io.BytesIO(b'%PDF-fixture'), wait=lambda **kwargs: 0, poll=lambda: 0)
    def command(args, **kwargs):
        calls.append(args)
        if 'rm' in args:
            raise RuntimeError('daemon unreachable')
    with pytest.raises(runner.CleanupFailure) as result:
        runner._convert('admincore-office-' + 'a' * 32, runner.container_args('admincore-office-' + 'a' * 32, source, IMAGE), command=command, popen=lambda *a, **k: process)
    owned_name = calls[0][calls[0].index('--name') + 1]
    assert result.value.container == owned_name
    assert calls[1:] == [['docker', 'rm', '--force', owned_name]] * 2


@pytest.mark.parametrize('failure', [False, True])
def test_once_protocol_tokens_stay_in_stdin_and_private_source_removed(monkeypatch, tmp_path, failure):
    source = b'private fixture bytes'
    identifier, token = str(uuid.uuid4()), 'd' * 64
    job = {'job_id': identifier, 'token': token, 'source': base64.b64encode(source).decode(),
        'source_sha256': hashlib.sha256(source).hexdigest(), 'extension': 'docx', 'engine': IMAGE}
    folder = tmp_path / ('admincore-office-' + identifier + '-fixture')
    folder.mkdir()
    calls = []
    def protocol(action, payload=None):
        calls.append((action, payload))
        return job if action == 'claim' else {'updated': True}
    def convert(path, image):
        assert path.read_bytes() == source and image == IMAGE
        if failure:
            raise TimeoutError('private parser error')
        return b'%PDF-fixture'
    monkeypatch.setattr(runner, 'protocol', protocol)
    monkeypatch.setattr(runner, 'convert', convert)
    monkeypatch.setattr(runner.tempfile, 'mkdtemp', lambda **kwargs: str(folder))
    monkeypatch.setattr(runner.tempfile, 'gettempdir', lambda: str(tmp_path))
    assert runner.once(IMAGE)
    assert calls[-1][1]['token'] == token
    if failure:
        assert calls[-1][0] == 'fail'
        assert not (folder / 'source.docx').exists()
        report = (folder / 'failure.json').read_text()
        assert 'conversion_timeout' in report and token not in report and 'private' not in report
    else:
        assert calls[-1][0] == 'finish' and not folder.exists()


def test_copy_failure_removes_unstarted_loader_and_private_volume(tmp_path):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'private fixture')
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[:2] == ['docker', 'cp']:
            raise RuntimeError('copy failed')
    with pytest.raises(RuntimeError, match='copy failed'):
        runner.convert(source, IMAGE, command=command)
    assert not any(args[:2] == ['docker', 'start'] for args in calls)
    assert calls[-2][:3] == ['docker', 'rm', '--force']
    assert calls[-1][:3] == ['docker', 'volume', 'rm']


def test_input_volume_cleanup_failure_stops_after_own_resource_retry(tmp_path):
    source = tmp_path / 'source.docx'
    source.write_bytes(b'private fixture')
    name = 'admincore-office-' + 'a' * 32
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[:3] == ['docker', 'volume', 'rm']:
            raise RuntimeError('volume busy')
    with pytest.raises(runner.CleanupFailure) as result:
        with runner.staged_source(name, source, IMAGE, command=command):
            pass
    assert result.value.container == name + '-input'
    assert calls[-2:] == [['docker', 'volume', 'rm', name + '-input']] * 2
