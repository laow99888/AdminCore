"""导出真实临时Git提交，验证版本来源、敏感目录隔离、冲突及项目归属。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import subprocess
from unittest.mock import patch

import pytest

SPEC = spec_from_file_location('create_project', Path(__file__).parents[1] / 'create_project.py')
module = module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    git(root, 'init')
    git(root, 'config', 'user.name', '导出测试')
    git(root, 'config', 'user.email', 'fixture@example.test')
    for name in module.REQUIRED:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('fixture\n', encoding='utf-8')
    (root / 'backend/config/base-version.json').write_text(json.dumps({'version': '0.1.0-dev.1'}), encoding='utf-8')
    (root / '.env.example').write_text('DJANGO_SECRET_KEY=placeholder\nDB_PASSWORD=placeholder\nADMINCORE_ADMIN_PASSWORD=\n# example\n', encoding='utf-8')
    for name in ('.env', '.env.admin-access.txt', 'backend/media/private.txt', 'backups/private.dump',
                 'frontend/node_modules/private.js', 'backend/venv/private.py'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('private-secret-value', encoding='utf-8')
    git(root, 'add', '-f', '.')
    git(root, 'commit', '-m', '建立隔离测试模板')
    return root


def create(source, target, **kwargs):
    with patch.object(module, 'check_ports'):
        return module.create_project(target, source=source, name='fixture-app', **kwargs)


def test_export_uses_commit_not_dirty_tree_and_excludes_private_files(source, tmp_path):
    (source / 'frontend/package-lock.json').write_text('dirty-secret', encoding='utf-8')
    (source / 'untracked.txt').write_text('untracked-secret', encoding='utf-8')
    target = tmp_path / 'generated'
    data = create(source, target)
    assert (target / 'frontend/package-lock.json').read_text(encoding='utf-8') == 'fixture\n'
    assert not (target / '.git').exists() and not (target / 'untracked.txt').exists()
    for path in ('.env.admin-access.txt', 'backend/media/private.txt', 'backups/private.dump',
                 'frontend/node_modules/private.js', 'backend/venv/private.py'):
        assert not (target / path).exists()
    env = (target / '.env').read_text(encoding='utf-8')
    assert 'placeholder' not in env and 'private-secret-value' not in env
    passwords = [line.partition('=')[2] for line in env.splitlines() if line.startswith(('DJANGO_SECRET_KEY=', 'DB_PASSWORD=', 'ADMINCORE_ADMIN_PASSWORD='))]
    assert len(passwords) == len(set(passwords)) == 3 and all(len(value) >= 50 for value in passwords)
    assert data['source_revision'] == git(source, 'rev-parse', 'HEAD')
    assert '.env' not in data['files'] and data['instance_id'] in (target / 'compose.project.yml').read_text()
    assert 'private-secret-value' not in json.dumps(data)


@pytest.mark.parametrize('name', ['AdminCore', '../project', 'x', 'a'*33, 'app;rm', '-app', 'app_1'])
def test_invalid_name_never_creates_target(source, tmp_path, name):
    target = tmp_path / 'refused'
    with pytest.raises(module.ProjectError):
        module.create_project(target, source=source, name=name)
    assert not target.exists()


def test_existing_and_in_source_targets_preserved(source, tmp_path):
    existing = tmp_path / 'exists'
    existing.mkdir()
    sentinel = existing / 'keep.txt'
    sentinel.write_text('user data')
    for target in (existing, source / 'nested'):
        with pytest.raises(module.ProjectError):
            create(source, target)
    assert sentinel.read_text() == 'user data' and not (source / 'nested').exists()


@pytest.mark.parametrize('path', ['../outside', '/outside', 'a/../../outside', 'C:/private', 'a\\b', 'a//b'])
def test_archive_path_rejects_escape(path):
    with pytest.raises(module.ProjectError):
        module.safe_source_path(path)


def test_ref_is_not_a_shell_or_git_option(source):
    for ref in ('--output=/private', 'HEAD;echo secret', 'HEAD\nsecret'):
        with pytest.raises(module.ProjectError):
            module.snapshot(source, ref)


def test_upgrade_report_is_read_only_and_detects_real_three_way_conflicts(source, tmp_path):
    target = tmp_path / 'generated'
    create(source, target)
    assert module.upgrade_plan(target, source)['changes'] == []
    local = target / 'frontend/package-lock.json'
    local.write_text('local edit', encoding='utf-8')
    upstream = source / 'frontend/package-lock.json'
    upstream.write_text('upstream edit', encoding='utf-8')
    (source / 'new-upstream.md').write_text('new', encoding='utf-8')
    git(source, 'add', '.')
    git(source, 'commit', '-m', '上游兼容修复')
    result = module.upgrade_plan(target, source)
    row = next(item for item in result['changes'] if item['path'] == 'frontend/package-lock.json')
    assert row['upstream_changed'] and row['local_changed'] and row['conflict']
    assert result['conflicts'] == 1 and result['read_only']
    assert local.read_text(encoding='utf-8') == 'local edit' and not (target / 'new-upstream.md').exists()
    assert 'local edit' not in json.dumps(result) and 'upstream edit' not in json.dumps(result)


def test_fixed_commands_do_not_offer_destructive_volume_removal(source, tmp_path):
    target = tmp_path / 'generated'
    create(source, target)
    assert module.compose_command(target, 'up')[-3:] == ['db', 'backend', 'frontend']
    assert module.compose_command(target, 'stop')[-1:] == ['stop']
    assert not any('--volumes' in value for value in module.compose_command(target, 'stop'))
    with pytest.raises(module.ProjectError):
        module.compose_command(target, 'down')


def test_foreign_project_resources_are_never_taken_over(source, tmp_path):
    target = tmp_path / 'generated'
    create(source, target)
    def docker(args, **kwargs):
        value = json.dumps({'io.admincore.instance': 'another-instance'}) if '--format' in args else 'foreign-id\n'
        return subprocess.CompletedProcess(args, 0, value, '')
    with patch.object(module.subprocess, 'run', side_effect=docker) as run:
        with pytest.raises(module.ProjectError, match='拒绝接管'):
            module.run_project(target, 'stop')
    assert not any('stop' in item.args[0] for item in run.call_args_list)


def test_ownership_matches_container_volume_and_network(source, tmp_path):
    target = tmp_path / 'generated'
    data = create(source, target)
    def docker(args, **kwargs):
        value = json.dumps({'io.admincore.instance': data['instance_id']}) if '--format' in args else 'own-id\n'
        return subprocess.CompletedProcess(args, 0, value, '')
    with patch.object(module.subprocess, 'run', side_effect=docker) as run:
        module.verify_ownership(target)
    assert run.call_count == 6


@pytest.mark.parametrize('ports', [(0, 9001), (9000, 9000), (70000, 9001), (True, 9001)])
def test_invalid_ports(ports):
    with pytest.raises(module.ProjectError):
        module.check_ports(*ports)


@pytest.mark.parametrize('field,value', [('schema_version', True), ('project_name', '--evil'),
    ('source_revision', 'HEAD'), ('instance_id', ''), ('files', {'../private': 'a'*64}),
    ('files', {'.env': 'a'*64}), ('base_version', None)])
def test_invalid_metadata_refused_even_when_python_optimized(source, tmp_path, field, value):
    target = tmp_path / 'generated'
    data = create(source, target)
    data[field] = value
    (target / module.META).write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(module.ProjectError):
        module.load_project(target)
    code = ('import sys;sys.path.insert(0,sys.argv[1]);from create_project import load_project;'
            'load_project(sys.argv[2])')
    result = subprocess.run([__import__('sys').executable, '-O', '-c', code,
        str(Path(module.__file__).parent), str(target)], capture_output=True)
    assert result.returncode != 0


def test_tracked_symlink_is_rejected_before_creating_target(source, tmp_path):
    digest = subprocess.run(
        ['git', '-C', str(source), 'hash-object', '-w', '--stdin'], input='../private',
        text=True, capture_output=True, check=True).stdout.strip()
    git(source, 'update-index', '--add', '--cacheinfo', '120000', digest, 'link')
    git(source, 'commit', '-m', '添加拒绝导出的链接')
    target = tmp_path / 'refused'
    with pytest.raises(module.ProjectError, match='链接'):
        create(source, target)
    assert not target.exists()


def test_environment_template_empty_values_remain_empty_in_compose(tmp_path):
    """Compose 对 KEY= 后的注释会作为值，不能只测试 python-dotenv。"""
    import shutil
    if not shutil.which('docker'):
        pytest.skip('需要 Docker Compose 的真实 env_file 解析器')
    example = Path(module.__file__).resolve().parents[1] / '.env.example'
    compose = tmp_path / 'compose.json'
    compose.write_text(json.dumps({'services': {'probe': {
        'image': 'postgres:18.6', 'env_file': [str(example)]}}}), encoding='utf-8')
    result = subprocess.run(['docker', 'compose', '--env-file', str(example), '-f', str(compose),
                             'config', '--format', 'json'], capture_output=True, text=True,
                            encoding='utf-8', timeout=30, check=True)
    environment = json.loads(result.stdout)['services']['probe']['environment']
    for key in ['ADMINCORE_TRUSTED_PROXIES', 'ADMINCORE_ADMIN_PASSWORD', 'S3_ENDPOINT_URL',
                'SSO_REDIRECT_URI', 'SSO_FRONTEND_ORIGIN', 'SSO_ENCRYPTION_KEY']:
        assert environment[key] == '', key


def test_failed_start_collects_only_owned_service_logs(source, tmp_path):
    target = tmp_path / 'generated'
    create(source, target)
    with patch.object(module, 'verify_ownership') as ownership, patch.object(module.subprocess, 'run') as run:
        run.side_effect = [subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)]
        with pytest.raises(module.ProjectError, match='启动失败'):
            module.run_project(target, 'up')
    ownership.assert_called_once_with(target.resolve())
    assert run.call_args_list[1].args[0][-6:] == ['logs', '--no-color', '--tail', '100', 'backend', 'db']


def test_start_retries_once_after_buildkit_status_stream_eof(source, tmp_path):
    target = tmp_path / 'generated'
    create(source, target)
    with patch.object(module, 'verify_ownership'), patch.object(module.subprocess, 'run') as run:
        def lose_stream(*args, **kwargs):
            kwargs['stdout'].write('target worker: failed to receive status: rpc error: code = Unavailable\n')
            return subprocess.CompletedProcess([], 1)
        calls = iter((lose_stream, lambda *args, **kwargs: subprocess.CompletedProcess([], 0)))
        run.side_effect = lambda *args, **kwargs: next(calls)(*args, **kwargs)
        assert module.run_project(target, 'up') == 0
    assert len(run.call_args_list) == 2
    assert run.call_args_list[1].args[0] == run.call_args_list[0].args[0]


def test_start_does_not_retry_for_an_old_buildkit_error(source, tmp_path):
    target = tmp_path / 'generated'
    create(source, target)
    folder = target / '.codex-validation'
    folder.mkdir()
    (folder / 'project-start.log').write_text('failed to receive status: rpc error: code = Unavailable\n')
    with patch.object(module, 'verify_ownership'), patch.object(module.subprocess, 'run') as run:
        run.side_effect = [subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)]
        with pytest.raises(module.ProjectError, match='启动失败'):
            module.run_project(target, 'up')
    assert run.call_args_list[1].args[0][-6:] == ['logs', '--no-color', '--tail', '100', 'backend', 'db']
