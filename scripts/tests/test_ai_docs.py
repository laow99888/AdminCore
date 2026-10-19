"""导航必须能用于定位，产品版本快照与下游导出不能脱节。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import shutil
import subprocess

import pytest

SPEC = spec_from_file_location('check_ai_docs', Path(__file__).parents[1] / 'check_ai_docs.py')
checker = module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_current_navigation_and_version_contract():
    result = checker.check()
    assert result['documents'] >= len(checker.CURRENT)
    assert result['local_links'] > 100


@pytest.fixture
def documentation_copy(tmp_path):
    root = tmp_path / 'repo'
    # 复制受管理文档和检查所需元数据；其他链接仅占位，不接触环境/业务数据。
    root.mkdir()
    files = checker.documentation_files(checker.ROOT)
    files.extend(checker.ROOT / path for path in (
        'frontend/package.json', 'frontend/package-lock.json', 'backend/config/base-version.json',
        'frontend/src/api/generated/openapi.json', 'backend/apps/core/modules.py'))
    for source in files:
        destination = root / source.relative_to(checker.ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for source in files:
        if source.suffix != '.md':
            continue
        for match in checker.LINK.finditer(source.read_text(encoding='utf-8')):
            parsed = checker.urlsplit(match[1].strip('<>'))
            if parsed.scheme or not parsed.path:
                continue
            original = (source.parent / checker.unquote(parsed.path)).resolve()
            if not original.is_relative_to(checker.ROOT) or not original.exists():
                continue
            target = root / original.relative_to(checker.ROOT)
            if original.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
    for source in checker.ROOT.joinpath('scripts').glob('*.py'):
        target = root / 'scripts' / source.name
        target.parent.mkdir(exist_ok=True)
        target.touch()
    return root


def test_broken_navigation_is_rejected(documentation_copy):
    checker.check(documentation_copy)
    with (documentation_copy / 'AGENTS.md').open('a', encoding='utf-8') as stream:
        stream.write('\n[失效入口](missing-file.py)\n')
    with pytest.raises(ValueError, match='无效本地链接'):
        checker.check(documentation_copy)


def test_new_registered_module_needs_navigation(documentation_copy):
    with (documentation_copy / 'backend/apps/core/modules.py').open('a', encoding='utf-8') as stream:
        stream.write('\nfrom apps.new_business.manifest import MODULE as NEW_MODULE\n')
    with pytest.raises(ValueError, match='new_business'):
        checker.check(documentation_copy)


def test_version_drift_is_rejected(documentation_copy):
    path = documentation_copy / 'backend/config/base-version.json'
    version = json.loads(path.read_text(encoding='utf-8'))
    version['version'] = '99.0.0'
    path.write_text(json.dumps(version), encoding='utf-8')
    with pytest.raises(ValueError, match='OpenAPI 不一致'):
        checker.check(documentation_copy)


@pytest.mark.parametrize('filename,keys', [
    ('package.json', ('version',)),
    ('package-lock.json', ('version',)),
    ('package-lock.json', ('packages', '', 'version')),
])
def test_frontend_version_drift_is_rejected(documentation_copy, filename, keys):
    path = documentation_copy / 'frontend' / filename
    content = json.loads(path.read_text(encoding='utf-8'))
    parent = content
    for key in keys[:-1]:
        parent = parent[key]
    parent[keys[-1]] = '99.0.0'
    path.write_text(json.dumps(content), encoding='utf-8')
    with pytest.raises(ValueError, match='前端 .*版本与产品版本不一致'):
        checker.check(documentation_copy)


def test_specialist_manual_is_checked(documentation_copy):
    with (documentation_copy / 'docs/字段级权限.md').open('a', encoding='utf-8') as stream:
        stream.write('\n[失效入口](missing-specialist.py)\n')
    with pytest.raises(ValueError, match='无效本地链接'):
        checker.check(documentation_copy)


def test_link_with_spaces_is_checked(documentation_copy):
    with (documentation_copy / 'AGENTS.md').open('a', encoding='utf-8') as stream:
        stream.write('\n[失效入口](<missing file.py>)\n')
    with pytest.raises(ValueError, match='无效本地链接'):
        checker.check(documentation_copy)


def test_unknown_frontend_command_is_rejected(documentation_copy):
    with (documentation_copy / 'docs/前端开发指南.md').open('a', encoding='utf-8') as stream:
        stream.write('\nnpm run imaginary:check\n')
    with pytest.raises(ValueError, match='imaginary:check'):
        checker.check(documentation_copy)


def test_documentation_anchor_is_checked(documentation_copy):
    with (documentation_copy / 'AGENTS.md').open('a', encoding='utf-8') as stream:
        stream.write('\n[错误章节](docs/前端开发指南.md#missing-heading)\n')
    with pytest.raises(ValueError, match='无效章节'):
        checker.check(documentation_copy)


def test_missing_validation_script_is_rejected(documentation_copy):
    (documentation_copy / 'scripts/check_ai_docs.py').unlink()
    with pytest.raises(ValueError, match='脚本不存在 scripts/check_ai_docs.py'):
        checker.check(documentation_copy)


def test_export_without_git_keeps_specialist_manuals(documentation_copy):
    assert not (documentation_copy / '.git').exists()
    files = checker.documentation_files(documentation_copy)
    assert documentation_copy / 'docs/字段级权限.md' in files
    assert documentation_copy / 'frontend/e2e/README.md' in files


def test_exported_project_entrypoint_is_checked(documentation_copy):
    (documentation_copy / 'PROJECT.md').write_text('[业务入口](missing-business.py)', encoding='utf-8')
    with pytest.raises(ValueError, match='PROJECT.md：无效本地链接'):
        checker.check(documentation_copy)


def test_code_example_does_not_create_an_anchor():
    content = '# 章节\n\n```markdown\n# 假章节\n```\n\n# 章节\n'
    assert checker.heading_ids(content) == {'章节', '章节-1'}


def test_git_scope_excludes_untracked_user_reports(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    subprocess.run(['git', 'init', str(root)], check=True, capture_output=True)
    tracked = root / 'tracked.md'
    tracked.write_text('# 正式手册', encoding='utf-8')
    subprocess.run(['git', '-C', str(root), 'add', 'tracked.md'], check=True, capture_output=True)
    report = root / 'user-report.md'
    report.write_text('[未核实审计](missing-file.py)', encoding='utf-8')
    files = checker.documentation_files(root)
    assert tracked in files
    assert report not in files


@pytest.mark.parametrize('target', ['.codex-validation/local.log', 'D:/AdminCore/.codex-validation/local.log'])
def test_private_evidence_link_is_rejected_even_if_present(documentation_copy, target):
    evidence = documentation_copy / '.codex-validation/local.log'
    evidence.parent.mkdir(exist_ok=True)
    evidence.write_text('isolated evidence', encoding='utf-8')
    with (documentation_copy / 'AGENTS.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n[仅本机存在]({target})\n')
    with pytest.raises(ValueError, match='私有验收证据应使用文字路径'):
        checker.check(documentation_copy)


def test_windows_drive_link_is_not_treated_as_an_external_url(documentation_copy):
    with (documentation_copy / 'AGENTS.md').open('a', encoding='utf-8') as stream:
        stream.write('\n[仅本机有效](D:/AdminCore/README.md)\n')
    with pytest.raises(ValueError, match='本地附件必须使用仓库相对路径'):
        checker.check(documentation_copy)
