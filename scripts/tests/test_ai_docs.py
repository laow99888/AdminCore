"""导航必须能用于定位，产品版本快照与下游导出不能脱节。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import shutil

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
    # 只复制当前导航及所链接的空路径占位，不接触环境/业务数据。
    root.mkdir()
    files = [checker.ROOT / path for path in checker.CURRENT]
    files.extend((checker.ROOT / 'docs/ai').glob('*.md'))
    files.extend(checker.ROOT / path for path in (
        'CHANGELOG.md', 'backend/config/base-version.json',
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
