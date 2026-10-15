"""生成模块隔离安装应兼容真实的条件扩展数组，并拒绝静默漏装路由。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = spec_from_file_location('codegen_validation', ROOT / 'scripts/validate_codegen.py')
validation = module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


@pytest.mark.parametrize('source', [
    'export const frontendExtensions = [{ key: "example" }] as const\n',
    'export const frontendExtensions = [] as const\n',
    (ROOT / 'frontend/src/modules/registry.ts').read_text(encoding='utf-8'),
])
def test_generated_routes_preserve_existing_conditional_extensions(tmp_path, source):
    registry = tmp_path / 'registry.ts'
    registry.write_text(source, encoding='utf-8')
    validation.register_frontend_extension(registry, 'work_assets', '资产记录')
    validation.register_frontend_extension(registry, 'catalog_items', '目录记录')
    result = registry.read_text(encoding='utf-8')
    anchor = 'export const frontendExtensions = ['
    inserted = result[len(source.partition(anchor)[0]) + len(anchor):]
    original_tail = source.partition(anchor)[2]
    assert inserted.endswith(original_tail)
    entries = inserted[:-len(original_tail)] if original_tail else inserted
    assert entries.count('key: "work_assets"') == 1
    assert entries.count('key: "catalog_items"') == 1
    for module in ('work_assets', 'catalog_items'):
        assert f'path: "/{module.replace("_", "-")}"' in entries
        assert f'permission: "{module}:read"' in entries
        assert f'import("../views/{module}/RecordListView.vue")' in entries
    assert result.startswith(source.partition(anchor)[0] + anchor)


@pytest.mark.parametrize('source', [
    'export const changedRegistry = [] as const\n',
    'export const frontendExtensions = []\nexport const frontendExtensions = []\n',
])
def test_changed_registry_contract_fails_before_build_without_modifying_source(tmp_path, source):
    registry = tmp_path / 'registry.ts'
    registry.write_text(source, encoding='utf-8')
    with pytest.raises(RuntimeError, match='前端扩展登记入口不唯一'):
        validation.register_frontend_extension(registry, 'work_assets', '资产记录')
    assert registry.read_text(encoding='utf-8') == source
