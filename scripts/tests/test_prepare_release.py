from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

SPEC = spec_from_file_location('prepare_release', Path(__file__).parents[1] / 'prepare_release.py')
release = module_from_spec(SPEC)
SPEC.loader.exec_module(release)
BACKEND = 'sha256:' + 'a' * 64
FRONTEND = 'sha256:' + 'b' * 64
DATABASE = 'sha256:' + 'c' * 64


@pytest.mark.parametrize('files,roles', [
    (['docker-compose.yml'], {'backend', 'worker', 'beat'}),
    (['docker-compose.yml', 'compose.minimal.yml'], {'backend'}),
    (['docker-compose.yml', 'compose.realtime.yml'], set(release.ROLES)),
    (['docker-compose.yml', 'compose.realtime.yml', 'compose.hardened.yml'], set(release.ROLES)),
])
def test_real_compose_definitions_support_shared_artifacts(tmp_path, files, roles):
    if not shutil.which('docker'):
        pytest.skip('需要 Docker Compose 配置解析器')
    root = Path(__file__).resolve().parents[2]
    # 服务自身也声明 env_file: .env；不能依赖开发机恰好存在的私有文件。
    (tmp_path / '.env').write_text((root / '.env.example').read_text(encoding='utf-8')
                                  + '\nDB_PASSWORD=synthetic-release-test-only\n', encoding='utf-8')
    args = ['docker', 'compose', '--project-directory', str(tmp_path), '--env-file', str(tmp_path / '.env')]
    for file in files:
        args += ['-f', str(root / file)]
    environment = {**os.environ, 'COMPOSE_PROFILES': ''}
    result = subprocess.run(args + ['config', '--format', 'json'], cwd=root, env=environment,
                            capture_output=True, text=True, encoding='utf-8', check=True, timeout=30)
    effective = json.loads(result.stdout)
    assert effective['services']['backend']['environment']['DB_PASSWORD'] == 'synthetic-release-test-only'
    assert set(effective['services']) & set(release.ROLES) == roles
    assert release.build_targets(effective) == ['backend', 'frontend']
    for name in ('backend', 'realtime'):
        service = effective['services'].get(name, {})
        if service.get('read_only'):
            assert service['environment']['XDG_RUNTIME_DIR'] == '/tmp'
            assert any(mount.startswith('/tmp:') for mount in service['tmpfs'])


def config():
    build = {'context': '/source/backend', 'args': {'ADMINCORE_BUILD_PROFILE': 'full'}}
    return {'name': 'fixture', 'services': {
        **{name: {'build': deepcopy(build), 'environment': {'PASSWORD': 'must-not-export'}}
           for name in release.ROLES},
        'frontend': {'build': {'context': '/source/frontend'}},
        'db': {'image': 'postgres:18.6'},
    }}


@pytest.mark.parametrize('role', ['worker', 'beat', 'realtime'])
def test_python_role_build_drift_is_rejected(role):
    definition = config()
    definition['services'][role]['build']['args']['ADMINCORE_BUILD_PROFILE'] = 'minimal'
    with pytest.raises(release.ReleaseError, match='构建定义不一致'):
        release.build_targets(definition)


def test_prepare_builds_once_pins_roles_and_never_exports_environment(tmp_path, monkeypatch):
    (tmp_path / 'compose.yml').write_text('services: {}')
    (tmp_path / '.env').write_text('PASSWORD=must-not-export')
    calls = []

    def command(args, root, **kwargs):
        calls.append(args)
        if 'config' in args:
            return json.dumps(config())
        if 'inspect' in args:
            return {'fixture-backend': BACKEND, 'fixture-frontend': FRONTEND, 'postgres:18.6': DATABASE}[args[3]]
        assert args[-3:] == ['build', 'backend', 'frontend']

    monkeypatch.setattr(release, 'command', command)
    output = tmp_path / 'release'
    manifest = release.prepare(tmp_path, ['compose.yml'], output)
    assert all(manifest['images'][role] == BACKEND for role in release.ROLES)
    assert manifest['images']['db'] == DATABASE
    assert sum('build' in call for call in calls) == 1
    for file in output.iterdir():
        assert 'must-not-export' not in file.read_text()
    with pytest.raises(release.ReleaseError, match='拒绝覆盖'):
        release.prepare(tmp_path, ['compose.yml'], output)


@pytest.mark.parametrize('image', ['backend:latest', 'sha256:bad', BACKEND + '\ncommand: evil'])
def test_overlay_rejects_mutable_or_malformed_images(image):
    with pytest.raises(release.ReleaseError):
        release.pinned_overlay({'backend': image})


@pytest.mark.parametrize('mismatch', ['image', 'running', 'health', 'build', 'missing'])
def test_verify_rejects_runtime_or_configuration_drift(tmp_path, monkeypatch, mismatch):
    (tmp_path / 'compose.yml').write_text('services: {}')
    (tmp_path / '.env').write_text('')
    output = tmp_path / 'release'
    output.mkdir()
    images = {'backend': BACKEND}
    (output / 'manifest.json').write_text(json.dumps({'schema_version': 1, 'project': 'fixture', 'images': images}))
    (output / 'compose.release.yml').write_text(release.pinned_overlay(images), encoding='utf-8')
    effective = {'name': 'fixture', 'services': {'backend': {'image': BACKEND, 'pull_policy': 'never'}}}
    details = {'Image': BACKEND, 'State': {'Running': True, 'Health': {'Status': 'healthy'}}}
    if mismatch == 'image': details['Image'] = FRONTEND
    if mismatch == 'running': details['State']['Running'] = False
    if mismatch == 'health': details['State']['Health']['Status'] = 'unhealthy'
    if mismatch == 'build': effective['services']['backend']['build'] = {'context': '/source'}

    def command(args, root, **kwargs):
        if 'config' in args: return json.dumps(effective)
        if 'ps' in args: return '' if mismatch == 'missing' else 'container'
        return json.dumps([details])

    monkeypatch.setattr(release, 'command', command)
    with pytest.raises(release.ReleaseError):
        release.verify(tmp_path, ['compose.yml'], output)


@pytest.mark.parametrize('instance', ['healthy', 'unhealthy', 'missing'])
def test_verify_excludes_oneoff_containers_but_requires_healthy_service(tmp_path, monkeypatch, instance):
    (tmp_path / 'compose.yml').write_text('services: {}')
    (tmp_path / '.env').write_text('')
    output = tmp_path / 'release'
    output.mkdir()
    images = {'backend': BACKEND}
    (output / 'manifest.json').write_text(json.dumps({'schema_version': 1, 'project': 'fixture', 'images': images}))
    (output / 'compose.release.yml').write_text(release.pinned_overlay(images), encoding='utf-8')
    effective = {'name': 'fixture', 'services': {'backend': {'image': BACKEND, 'pull_policy': 'never'}}}
    details = {
        'probe': {'Image': FRONTEND, 'Config': {'Labels': {'com.docker.compose.oneoff': 'True'}},
                  'State': {'Running': False, 'Health': {'Status': 'unhealthy'}}},
        'service': {'Image': BACKEND, 'Config': {'Labels': {'com.docker.compose.oneoff': 'False'}},
                    'State': {'Running': True, 'Health': {'Status': instance}}},
    }

    def command(args, root, **kwargs):
        if 'config' in args:
            return json.dumps(effective)
        if 'ps' in args:
            return 'probe' if instance == 'missing' else 'probe\nservice'
        return json.dumps([details[args[-1]]])

    monkeypatch.setattr(release, 'command', command)
    if instance == 'healthy':
        assert release.verify(tmp_path, ['compose.yml'], output)['passed']
    else:
        with pytest.raises(release.ReleaseError):
            release.verify(tmp_path, ['compose.yml'], output)
