"""导出真实一次性Git模板；演示凭据与目标隔离，错误确认不执行Docker。"""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
SPEC = spec_from_file_location('demo_project', Path(__file__).parents[1] / 'demo_project.py')
module = module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def source(tmp_path):
    from create_project import REQUIRED
    root = tmp_path / 'source'
    root.mkdir()
    git(root, 'init')
    git(root, 'config', 'user.name', '演示模板测试')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    for name in (*REQUIRED, 'backend/config/settings/demo.py',
            'backend/apps/core/management/commands/demo_admincore.py', 'scripts/demo_project.py'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture\n', encoding='utf-8')
    (root / 'backend/config/base-version.json').write_text(json.dumps({'version': '0.1.0-dev.1'}), encoding='utf-8')
    (root / '.env.example').write_text('DJANGO_ENV=production\nADMINCORE_PRESET=standard\n'
        'DB_NAME=admincore\nADMINCORE_ADMIN_PASSWORD=\nNOTIFICATION_EMAIL_ENABLED=False\n', encoding='utf-8')
    (root / '.env').write_text('private-production-value', encoding='utf-8')
    git(root, 'add', '-f', '.')
    git(root, 'commit', '-m', '建立专属演示模板夹具')
    return root


def create(source, target):
    with patch('create_project.check_ports'):
        return module.create_demo(target, source=source)


def test_create_demo_has_fresh_credentials_database_labels_and_nonproduction_override(source, tmp_path):
    first = tmp_path / 'demo-one'
    second = tmp_path / 'demo-two'
    one = create(source, first)
    two = create(source, second)
    assert one['demo_instance'] != two['demo_instance']
    assert one['database_name'] == 'admincore_demo_' + one['demo_instance']
    assert one['project_name'].startswith('admincore-demo-')
    environments = []
    for root, data in ((first, one), (second, two)):
        text = (root / '.env').read_text(encoding='utf-8')
        assert 'private-production-value' not in text
        environment = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        environments.append(environment)
        assert environment['DJANGO_ENV'] == 'demo' and environment['ADMINCORE_PRESET'] == 'demo'
        assert environment['DB_NAME'] == data['database_name']
        assert environment['ADMINCORE_ADMIN_USERNAME'] == 'demo_admin'
        assert environment['NOTIFICATION_EMAIL_ENABLED'] == 'False'
        assert environment['ADMINCORE_NOTIFICATION_EXTERNAL_CHANNELS_JSON'] == '{}'
        keys = ('ADMINCORE_ADMIN_PASSWORD', 'ADMINCORE_DEMO_EDITOR_PASSWORD', 'ADMINCORE_DEMO_VIEWER_PASSWORD')
        assert len({environment[key] for key in keys}) == 3
        assert all(len(environment[key]) >= 40 for key in keys)
        public = (root / module.DEMO_META).read_text(encoding='utf-8') + (root / 'PROJECT.md').read_text(encoding='utf-8')
        assert all(environment[key] not in public for key in (*keys, 'ADMINCORE_DEMO_RESET_TOKEN'))
        override = (root / 'compose.project.yml').read_text(encoding='utf-8')
        assert override.count('DJANGO_ENV: demo') == 3
        assert override.count('DJANGO_SETTINGS_MODULE: config.settings.demo') == 3
        assert data['project_instance'] in override and '127.0.0.1:${FRONTEND_PORT}:80' in override
    assert environments[0]['ADMINCORE_ADMIN_PASSWORD'] != environments[1]['ADMINCORE_ADMIN_PASSWORD']


def test_missing_demo_commit_fails_without_starting_services(source, tmp_path):
    git(source, 'rm', 'backend/config/settings/demo.py')
    git(source, 'commit', '-m', '构造不完整旧模板')
    with pytest.raises(module.ProjectError, match='不包含完整演示'):
        create(source, tmp_path / 'old-source')


def test_bad_confirmation_and_foreign_metadata_never_reach_docker(source, tmp_path):
    root = tmp_path / 'demo'
    data = create(source, root)
    with patch.object(module, 'verify_ownership') as ownership, patch.object(module.subprocess, 'run') as run:
        with pytest.raises(module.ProjectError, match='未停止或修改'):
            module.reset_demo(root, confirm_instance='wrong')
        ownership.assert_not_called()
        run.assert_not_called()
        data['project_instance'] = 'f' * 32
        (root / module.DEMO_META).write_text(json.dumps(data), encoding='utf-8')
        with pytest.raises(module.ProjectError):
            module.reset_demo(root, confirm_instance=data['demo_instance'])
        ownership.assert_not_called()
        run.assert_not_called()


def test_reset_stops_writers_before_owned_target_and_hides_token_from_argv(source, tmp_path):
    root = tmp_path / 'demo'
    data = create(source, root)
    token = next(line.split('=', 1)[1] for line in (root / '.env').read_text().splitlines()
                 if line.startswith('ADMINCORE_DEMO_RESET_TOKEN='))
    with patch.object(module, 'verify_ownership') as ownership, patch.object(module.subprocess, 'run') as run:
        run.return_value.returncode = 0
        module.reset_demo(root, confirm_instance=data['demo_instance'])
        ownership.assert_called_once_with(root)
        calls = [call.args[0] for call in run.call_args_list]
        assert calls[0][-5:] == ['stop', 'frontend', 'worker', 'beat', 'backend']
        assert calls[1][-7:-1] == ['run', '--rm', '--no-deps', 'backend', 'python', '-c']
        assert calls[2][-5:] == ['up', '-d', '--wait', '--wait-timeout', '180']
        assert all(token not in str(call) for call in calls)
        assert all(call[call.index('-p') + 1] == data['project_name'] for call in calls)


def test_failed_reset_keeps_writers_stopped_for_diagnosis(source, tmp_path):
    root = tmp_path / 'demo'
    data = create(source, root)
    with patch.object(module, 'verify_ownership'), patch.object(module.subprocess, 'run') as run:
        run.return_value.returncode = 1
        with pytest.raises(module.ProjectError, match='保持停止'):
            module.reset_demo(root, confirm_instance=data['demo_instance'])
        assert len(run.call_args_list) == 2
        assert not any('up' in call.args[0] for call in run.call_args_list)
