"""真实Git提交和独立业务副本的连续升级、失败恢复及路径边界。"""
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_upgrade as upgrade
from test_create_project import create, git, module, source  # noqa: F401


def commit(source, path, content):
    file = source / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding='utf-8')
    git(source, 'add', '.')
    git(source, 'commit', '-m', '推进上游测试版本')


def test_two_upgrades_preserve_business_and_advance_only_after_validation(source, tmp_path):
    root = tmp_path / 'project'
    original = create(source, root)
    environment = (root / '.env').read_bytes()
    (root / 'business.py').write_text('业务代码', encoding='utf-8')
    (root / 'docker-compose.yml').write_text('业务配置', encoding='utf-8')
    for iteration in range(2):
        commit(source, 'frontend/package-lock.json', f'upstream-{iteration}')
        plan = module.upgrade_plan(root, source)
        upgrade.apply_upgrade(root, source, plan)
        assert module.load_project(root)['source_revision'] != plan['to_revision']
        upgrade.accept_upgrade(root, [[sys.executable, '-c', 'import pathlib; assert pathlib.Path("business.py").is_file()']])
        assert module.load_project(root)['source_revision'] == plan['to_revision']
        assert not (root / upgrade.WORK).exists()
        assert not any(row['upstream_changed'] for row in module.upgrade_plan(root, source)['changes'])
    assert (root / 'business.py').read_text(encoding='utf-8') == '业务代码'
    assert (root / 'docker-compose.yml').read_text(encoding='utf-8') == '业务配置'
    assert (root / '.env').read_bytes() == environment
    assert module.load_project(root)['instance_id'] == original['instance_id']
    assert len(list((root / '.codex-validation/project-upgrades').iterdir())) == 2


def test_conflicts_require_explicit_decisions_and_keep_is_new_local_delta(source, tmp_path):
    root = tmp_path / 'project'; create(source, root)
    file = root / 'frontend/package-lock.json'; file.write_text('local')
    commit(source, 'frontend/package-lock.json', 'upstream')
    plan = module.upgrade_plan(root, source)
    with pytest.raises(upgrade.ProjectError, match='冲突决策'):
        upgrade.apply_upgrade(root, source, plan)
    assert not (root / upgrade.WORK).exists()
    upgrade.apply_upgrade(root, source, plan, keep_local=['frontend/package-lock.json'])
    upgrade.accept_upgrade(root, [[sys.executable, '-c', 'pass']])
    row = next(row for row in module.upgrade_plan(root, source)['changes'] if row['path'] == 'frontend/package-lock.json')
    assert row['local_changed'] and not row['upstream_changed'] and file.read_text() == 'local'


def test_failed_validation_keeps_baseline_and_restore_preserves_unrelated_data(source, tmp_path):
    root = tmp_path / 'project'; original = create(source, root)
    commit(source, 'frontend/package-lock.json', 'updated')
    commit(source, 'new-file.py', 'new')
    upgrade.apply_upgrade(root, source, module.upgrade_plan(root, source))
    (root / 'business.py').write_text('keep')
    with pytest.raises(upgrade.ProjectError, match='验收未通过'):
        upgrade.accept_upgrade(root, [[sys.executable, '-c', 'print("validation failed"); raise SystemExit(1)']])
    assert module.load_project(root) == original
    assert 'validation failed' in (root / upgrade.WORK / 'validation.log').read_text()
    upgrade.restore_upgrade(root)
    assert not (root / 'new-file.py').exists()
    assert (root / 'frontend/package-lock.json').read_text() == 'fixture\n'
    assert (root / 'business.py').read_text() == 'keep'


def test_stale_plan_and_post_apply_edit_cannot_be_overwritten(source, tmp_path):
    root = tmp_path / 'project'; create(source, root)
    commit(source, 'new-file.py', 'new')
    plan = module.upgrade_plan(root, source)
    file = root / 'new-file.py'; file.write_text('user data')
    with pytest.raises(upgrade.ProjectError, match='过期'):
        upgrade.apply_upgrade(root, source, plan)
    plan = module.upgrade_plan(root, source)
    upgrade.apply_upgrade(root, source, plan, take_upstream=['new-file.py'])
    file.write_text('another edit')
    with pytest.raises(upgrade.ProjectError, match='源码已变化'):
        upgrade.accept_upgrade(root, [[sys.executable, '-c', 'pass']])
    with pytest.raises(upgrade.ProjectError, match='拒绝覆盖'):
        upgrade.restore_upgrade(root)
    assert file.read_text() == 'another edit'


def test_explicit_source_delete_and_interrupted_apply_are_recoverable(source, tmp_path):
    root = tmp_path / 'project'; create(source, root)
    (source / 'frontend/package-lock.json').unlink()
    # 删除非 REQUIRED 文件才是有效底座提交。
    commit(source, 'obsolete.py', 'old')
    (source / 'frontend/package-lock.json').write_text('fixture\n')
    git(source, 'add', '.'); git(source, 'commit', '-m', '恢复必需文件')
    root2 = tmp_path / 'project2'; create(source, root2)
    (source / 'obsolete.py').unlink()
    commit(source, 'another.py', 'new')
    plan = module.upgrade_plan(root2, source)
    with pytest.raises(upgrade.ProjectError, match='allow-delete'):
        upgrade.apply_upgrade(root2, source, plan)
    original_write = upgrade.atomic_write
    def fail_new_file(path, content, mode):
        if path == root2 / 'another.py':
            raise OSError('simulated interrupted write')
        return original_write(path, content, mode)
    with patch.object(upgrade, 'atomic_write', side_effect=fail_new_file):
        with pytest.raises(upgrade.ProjectError, match='应用未完成'):
            upgrade.apply_upgrade(root2, source, plan, allow_delete=True)
    upgrade.restore_upgrade(root2)
    assert (root2 / 'obsolete.py').read_text() == 'old'
    upgrade.apply_upgrade(root2, source, module.upgrade_plan(root2, source), allow_delete=True)
    assert not (root2 / 'obsolete.py').exists()


@pytest.mark.parametrize('names', [('.env',), ('compose.project.yml',), ('x', 'X'), ('x', 'x/y'), ('x', 'X/y'), ('CON.py',), ('x./y',)])
def test_unsafe_and_reserved_paths_refused(names):
    with pytest.raises(upgrade.ProjectError):
        upgrade.validate_names(names)


def test_nonfile_ancestor_refused_without_mutation(source, tmp_path):
    root = tmp_path / 'project'; create(source, root)
    commit(source, 'extension/new.py', 'new')
    (root / 'extension').write_text('business file')
    plan = module.upgrade_plan(root, source)
    with pytest.raises(upgrade.ProjectError, match='不安全路径'):
        upgrade.apply_upgrade(root, source, plan, take_upstream=['extension/new.py'])
    assert (root / 'extension').read_text() == 'business file'


def test_live_lock_and_invalid_checks_never_run_commands(source, tmp_path):
    root = tmp_path / 'project'; create(source, root)
    (root / upgrade.LOCK).write_text('123')
    with pytest.raises(upgrade.ProjectError, match='已有升级命令'):
        upgrade.apply_upgrade(root, source, module.upgrade_plan(root, source))
    for checks in ([], 'echo pass', [['']], [[]]):
        with pytest.raises(upgrade.ProjectError, match='验收命令'):
            upgrade.accept_upgrade(root, checks)


def test_cli_plan_apply_and_accept_work_from_an_exported_project(source, tmp_path):
    import subprocess
    scripts = Path(upgrade.__file__).parent
    for name in ('create_project.py', 'project.py', 'project_upgrade.py'):
        (source / 'scripts' / name).write_bytes((scripts / name).read_bytes())
    git(source, 'add', '.'); git(source, 'commit', '-m', '导出真实运维工具')
    root = tmp_path / 'project'; create(source, root)
    commit(source, 'new-feature.py', 'feature')
    plan, checks = root / 'plan.json', root / 'checks.json'
    checks.write_text(json.dumps([[sys.executable, '-c', 'import pathlib; assert pathlib.Path("new-feature.py").read_text() == "feature"']]))
    def cli(*args):
        result = subprocess.run([sys.executable, str(root / 'scripts/project.py'), *args], cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
        assert result.returncode == 0, result.stderr
        return result
    cli('upgrade-plan', '--source', str(source), '--output', str(plan))
    cli('upgrade-apply', '--source', str(source), '--plan', str(plan))
    cli('upgrade-accept', '--checks', str(checks))
    assert module.load_project(root)['source_revision'] == git(source, 'rev-parse', 'HEAD')


def test_validation_cannot_change_source_then_advance_baseline(source, tmp_path):
    root = tmp_path / 'project'; original = create(source, root)
    commit(source, 'feature.py', 'feature')
    upgrade.apply_upgrade(root, source, module.upgrade_plan(root, source))
    with pytest.raises(upgrade.ProjectError, match='源码已变化'):
        upgrade.accept_upgrade(root, [[sys.executable, '-c', 'import pathlib; pathlib.Path("feature.py").write_text("changed")']])
    assert module.load_project(root) == original


def test_accept_recovers_after_metadata_or_archive_interruption(source, tmp_path):
    root = tmp_path / 'project'; create(source, root)
    commit(source, 'feature.py', 'feature')
    plan = module.upgrade_plan(root, source); upgrade.apply_upgrade(root, source, plan)
    original = upgrade.json_write
    def interrupted(path, value):
        if path == root / module.META:
            raise OSError('simulated metadata interruption')
        original(path, value)
    with patch.object(upgrade, 'json_write', side_effect=interrupted):
        with pytest.raises(OSError):
            upgrade.accept_upgrade(root, [[sys.executable, '-c', 'pass']])
    upgrade.accept_upgrade(root, [[sys.executable, '-c', 'pass']])
    assert module.load_project(root)['source_revision'] == plan['to_revision']
