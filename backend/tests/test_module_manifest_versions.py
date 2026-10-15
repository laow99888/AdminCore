"""安装时契约校验、依赖闭包和显式互斥，不装载外部代码或改变权限种子。"""
from dataclasses import replace
from io import StringIO
import json
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command, CommandError

from apps.core.contracts import Module, validate_registry
from apps.core.modules import MODULES, capabilities, resolve_modules
from apps.core.version import MODULE_CONTRACT_VERSION


def declaration(key, **options):
    return Module(key, key, key, 'apps.' + key + '.urls', ('/' + key,), **options)


@pytest.mark.parametrize('options', [dict(contract_version=2), dict(contract_version=True),
    dict(contract_version=0), dict(default_enabled='false'), dict(conflicts=('missing',)),
    dict(conflicts=('alpha',)), dict(conflicts=('beta', 'beta')), dict(dependencies=('beta', 'beta'))])
def test_invalid_contract_metadata_rejected(options):
    with pytest.raises(ImproperlyConfigured):
        validate_registry((declaration('alpha', **options), declaration('beta')))


@pytest.mark.parametrize('modules', [
    (declaration('alpha', dependencies=('beta',)), declaration('beta', conflicts=('alpha',))),
    (declaration('alpha', dependencies=('beta',)), declaration('beta', dependencies=('gamma',)),
     declaration('gamma', conflicts=('alpha',))),
    (declaration('alpha', dependencies=('beta', 'gamma')), declaration('beta', conflicts=('gamma',)), declaration('gamma')),
    (declaration('alpha', dependencies=('beta',)), declaration('beta', dependencies=('alpha',))),
])
def test_dependency_closure_cannot_require_conflicting_or_cyclic_modules(modules):
    with pytest.raises(ImproperlyConfigured):
        validate_registry(modules)


def test_one_sided_conflict_is_enforced_without_enabling_or_disabling_others():
    modules = (declaration('alpha', conflicts=('beta',)), declaration('beta'))
    presets = {'minimal': (), 'standard': ('alpha', 'beta')}
    with patch('apps.core.modules.MODULES', modules), patch('apps.core.modules.PRESETS', presets):
        assert resolve_modules('minimal', 'beta') == ('beta',)
        assert resolve_modules('minimal', 'alpha') == ('alpha',)
        for explicit in ('alpha,beta', 'beta,alpha', None):
            with pytest.raises(ImproperlyConfigured, match='互斥'):
                resolve_modules('standard', explicit)


def test_all_builtin_and_extension_modules_report_supported_metadata(settings):
    validate_registry(MODULES)
    settings.ADMINCORE_MODULES = ()
    for actual, declared in zip(capabilities()['modules'], MODULES, strict=True):
        assert actual['contract_version'] == declared.contract_version == MODULE_CONTRACT_VERSION
        assert actual['default_enabled'] is declared.default_enabled
        assert actual['conflicts'] == list(declared.conflicts)
        assert not actual['enabled']


def test_large_dependency_dag_is_bounded_and_not_exponentially_walked():
    modules = tuple(declaration('module' + str(index), dependencies=tuple('module' + str(previous)
        for previous in range(index))) for index in range(30))
    validate_registry(modules)
    with pytest.raises(ImproperlyConfigured):
        validate_registry(())
    with pytest.raises(ImproperlyConfigured):
        validate_registry(tuple(replace(modules[0], key='module' + str(index)) for index in range(129)))


def test_readonly_preflight_reports_disable_enable_and_keeps_current_settings(settings):
    settings.ADMINCORE_PRESET = 'standard'
    settings.ADMINCORE_MODULES = ('files', 'tasks')
    output = StringIO()
    call_command('check_modules', preset='minimal', modules='example', stdout=output)
    data = json.loads(output.getvalue())
    assert data['modules'] == data['enable'] == ['example']
    assert data['disable'] == ['files', 'tasks'] and data['requires_restart']
    assert data['retains_tables_and_data']
    assert settings.ADMINCORE_MODULES == ('files', 'tasks') and settings.ADMINCORE_PRESET == 'standard'
    output = StringIO()
    call_command('check_modules', stdout=output)
    assert not json.loads(output.getvalue())['requires_restart']
    with pytest.raises(CommandError, match='需要'):
        call_command('check_modules', modules='data_io', stdout=StringIO())


def test_preflight_preset_defaults_empty_selection_and_production_guard(settings, monkeypatch):
    settings.ADMINCORE_MODULES = ('files',)
    output = StringIO()
    call_command('check_modules', preset='minimal', stdout=output)
    assert json.loads(output.getvalue())['modules'] == []
    output = StringIO()
    call_command('check_modules', modules='', stdout=output)
    assert json.loads(output.getvalue())['modules'] == []
    monkeypatch.setenv('DJANGO_ENV', 'production')
    with pytest.raises(CommandError, match='生产环境禁止'):
        call_command('check_modules', preset='demo', stdout=StringIO())
