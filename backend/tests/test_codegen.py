"""验证生成边界、真实差异/计划保护及失败恢复；产物运行另由隔离集成验收。"""
import ast
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from apps.core.codegen.spec import GenerationError, parse_definition
from apps.core.codegen.render import render
from apps.core.codegen import plans


def definition():
    return {'module': 'work_assets', 'title': '资产记录', 'model': 'AssetRecord', 'fields': [
        {'name': 'label', 'label': '名称', 'kind': 'string', 'max_length': 80},
        {'name': 'remarks', 'label': '备注', 'kind': 'text', 'required': False},
        {'name': 'quantity', 'label': '数量', 'kind': 'integer', 'minimum': 0, 'maximum': 100},
        {'name': 'available', 'label': '可用', 'kind': 'boolean', 'default': True}]}


@pytest.mark.parametrize('change', [
    {'module': 'users'}, {'module': 'core'}, {'module': 'auth_app'}, {'module': 'permissions'},
    {'module': 'logs'}, {'module': 'example'}, {'module': 'files'}, {'module': '../unsafe'},
    {'module': 'con'}, {'module': 'class'}, {'module': 'x' * 21}, {'model': 'bad;import os'},
    {'model': 'None'}, {'fields': []}, {'fields': [{}]}, {'fields': [{'name': 'password', 'label': '密码', 'kind': 'string'}]},
    {'fields': [{'name': 'clean_fields', 'label': '字段', 'kind': 'string'}]},
    {'fields': [{'name': 'label', 'label': '字段', 'kind': 'decimal'}]},
    {'table': 'users_user'}, {'table': 'x;drop table y'}, {'title': '多行\n标题'}, {'unknown': True},
    {'fields': [{'name': 'label', 'label': '字段', 'kind': 'boolean', 'default': 1}]},
    {'fields': [{'name': 'label', 'label': '字段', 'kind': 'integer', 'minimum': 4, 'maximum': 1}]},
    {'fields': [{'name': 'label', 'label': '字段', 'kind': 'string', 'max_length': True}]},
    {'fields': [{'name': 'label', 'label': '字段', 'kind': 'string', 'required': 'true'}]},
    {'fields': [{'name': 'label', 'label': '字段', 'kind': 'string', 'minimum': 0}]},
    {'fields': [{'name': 'label', 'label': '字段', 'kind': 'text', 'default': '\x00'}]},
])
def test_invalid_definitions_fail_before_output(change):
    with pytest.raises(GenerationError):
        parse_definition({**definition(), **change})


def test_duplicate_sensitive_and_shadow_fields():
    for name in ['label', 'creator_id', 'api_token', 'private_key', 'save', 'a__b']:
        raw = definition()
        raw['fields'].append({'name': name, 'label': '字段', 'kind': 'string'})
        with pytest.raises(GenerationError):
            parse_definition(raw)


def test_literal_escaping_and_deterministic_render():
    raw = definition()
    raw['title'] = "</script>@@MODULE@@'标题"
    raw['fields'][1]['default'] = "</script>@@MODEL@@\u2028'\n"
    files = render(parse_definition(raw))
    assert files == render(parse_definition(raw)) and len(files) == 12
    page = files['frontend/src/views/work_assets/RecordListView.vue']
    assert page.count('</script>') == 1 and '\\u003c/script\\u003e@@MODEL@@' in page
    for name, code in files.items():
        if name.endswith('.py'):
            ast.parse(code)
    assert "'/work-assets/records/'" in page


def test_long_module_prefix_does_not_collide_indexes_or_openapi():
    outputs = []
    for suffix in ['aaa', 'bbb']:
        raw = definition(); raw['module'] = 'similar_prefix_' + suffix
        files = render(parse_definition(raw)); outputs.append(files)
        assert "name='similar_prefix_" + suffix + "_owner_ts'" in files[f"backend/apps/{raw['module']}/models.py"]
        assert "component_name='" + raw['module'] + "_AssetRecord'" in files[f"backend/apps/{raw['module']}/serializers.py"]
    assert outputs[0] != outputs[1]


@pytest.mark.parametrize('name', ['/absolute', '../escape', 'a/../escape', 'a//b', './a', 'a\\b', 'C:/file', 'a/'])
def test_reject_unbounded_or_normalized_paths(tmp_path, name):
    with pytest.raises(GenerationError):
        plans.safe_target(tmp_path, name)


def test_default_preview_no_writes_and_plan_not_overwritten(tmp_path):
    source = tmp_path / 'definition.json'
    source.write_text(json.dumps(definition()), encoding='utf-8')
    root, output = tmp_path / 'new-output', StringIO()
    call_command('generate_module', definition=str(source), output=str(root), stdout=output)
    assert not root.exists() and '--- before/' in output.getvalue() and '"state": "new"' in output.getvalue()
    plan = tmp_path / 'plan.json'
    call_command('generate_module', definition=str(source), output=str(root), plan=str(plan), stdout=StringIO())
    original = plan.read_bytes()
    with pytest.raises(CommandError):
        call_command('generate_module', definition=str(source), output=str(root), plan=str(plan), stdout=StringIO())
    assert plan.read_bytes() == original and not root.exists()


def test_selected_write_backup_and_unselected_untouched(tmp_path):
    raw = definition(); files = render(parse_definition(raw))
    name = 'backend/apps/work_assets/models.py'
    original = plans.safe_target(tmp_path, name)
    original.parent.mkdir(parents=True)
    original.write_text('# 用户手工内容\n', encoding='utf-8')
    plan = plans.make_plan(tmp_path, raw, files)
    result = plans.apply_plan(tmp_path, plan, raw, files, [name])
    assert original.read_text(encoding='utf-8') == files[name]
    assert (Path(result['backup']) / '0.original').read_text(encoding='utf-8') == '# 用户手工内容\n'
    assert not (tmp_path / 'frontend').exists() and not (tmp_path / '.codex-validation/codegen.lock').exists()


def test_stale_plan_hash_checks_before_any_write(tmp_path):
    raw = definition(); files = render(parse_definition(raw)); plan = plans.make_plan(tmp_path, raw, files)
    names = list(files)[:2]
    changed = plans.safe_target(tmp_path, names[1]); changed.parent.mkdir(parents=True)
    changed.write_text('new external data', encoding='utf-8')
    with pytest.raises(GenerationError, match='重新预览'):
        plans.apply_plan(tmp_path, plan, raw, files, names)
    assert not plans.safe_target(tmp_path, names[0]).exists()
    assert changed.read_text() == 'new external data'


@pytest.mark.parametrize('selected', [[], ['bogus'], ['a', 'a'], [1]])
def test_invalid_selection(tmp_path, selected):
    with pytest.raises(GenerationError):
        plans.apply_plan(tmp_path, plans.make_plan(tmp_path, {}, {'a': 'x'}), {}, {'a': 'x'}, selected)


@pytest.mark.parametrize('entries', [None, {}, [None], [{'path': []}], [{'path': 'a'}, {'path': 'a'}]])
def test_malformed_plan_friendly_error(tmp_path, entries):
    with pytest.raises(GenerationError):
        plans.apply_plan(tmp_path, {'plan_version': 1, 'definition': {}, 'entries': entries}, {}, {'a': 'x'}, ['a'])


def test_renderer_change_requires_new_preview(tmp_path):
    plan = plans.make_plan(tmp_path, {}, {'a': 'x'})
    with pytest.raises(GenerationError):
        plans.apply_plan(tmp_path, plan, {}, {'a': 'y'}, ['a'])
    assert not (tmp_path / 'a').exists()


def test_failed_second_write_restores_old_and_removes_own_new(tmp_path, monkeypatch):
    files = {'a': 'new', 'b': 'new'}; (tmp_path / 'a').write_text('original', encoding='utf-8')
    plan = plans.make_plan(tmp_path, {}, files); replace = plans.os.replace; calls = []
    def fail_second(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError('injected disk failure')
        return replace(source, target)
    monkeypatch.setattr(plans.os, 'replace', fail_second)
    with pytest.raises(OSError):
        plans.apply_plan(tmp_path, plan, {}, files, ['a', 'b'])
    assert (tmp_path / 'a').read_text() == 'original' and not (tmp_path / 'b').exists()
    assert len(list((tmp_path / '.codex-validation').glob('codegen-*/failed.json'))) == 1


def test_rollback_never_overwrites_external_edits(tmp_path, monkeypatch):
    files = {'a': 'new', 'b': 'new'}; plan = plans.make_plan(tmp_path, {}, files); replace = plans.os.replace
    def fail_second(source, target):
        if Path(target).name == 'b':
            (tmp_path / 'a').write_text('external edit', encoding='utf-8')
            raise OSError('injected disk failure')
        return replace(source, target)
    monkeypatch.setattr(plans.os, 'replace', fail_second)
    with pytest.raises(GenerationError, match='外部修改'):
        plans.apply_plan(tmp_path, plan, {}, files, ['a', 'b'])
    assert (tmp_path / 'a').read_text() == 'external edit'
    assert len(list((tmp_path / '.codex-validation').glob('codegen-*/rollback-conflicts.json'))) == 1


def test_existing_generation_lock_not_removed(tmp_path):
    folder = tmp_path / '.codex-validation'; folder.mkdir(); (folder / 'codegen.lock').write_text('other task')
    with pytest.raises(GenerationError, match='生成器锁'):
        plans.apply_plan(tmp_path, plans.make_plan(tmp_path, {}, {'a': 'x'}), {}, {'a': 'x'}, ['a'])
    assert (folder / 'codegen.lock').read_text() == 'other task' and not (tmp_path / 'a').exists()


def test_symlink_parent_or_backup_not_followed(tmp_path):
    outside = tmp_path / 'outside'; outside.mkdir(); root = tmp_path / 'root'; root.mkdir()
    try:
        (root / 'linked').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('当前Windows会话不允许创建符号链接；Linux CI执行此边界用例')
    with pytest.raises(GenerationError):
        plans.make_plan(root, {}, {'linked/file': 'x'})
    (root / '.codex-validation').symlink_to(outside, target_is_directory=True)
    with pytest.raises(GenerationError):
        plans.apply_plan(root, plans.make_plan(root, {}, {'file': 'x'}), {}, {'file': 'x'}, ['file'])
    assert not list(outside.iterdir())


def test_non_text_and_oversized_definition_fail(tmp_path):
    (tmp_path / 'a').write_bytes(b'\xff\xfe')
    with pytest.raises(GenerationError):
        plans.preview_diff(tmp_path, {'a': 'new'})
    source = tmp_path / 'huge.json'; source.write_bytes(b' ' * (1024 * 1024 + 1))
    with pytest.raises(CommandError):
        call_command('generate_module', definition=str(source), output=str(tmp_path), stdout=StringIO())
