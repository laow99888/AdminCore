"""真实离线 schema 的启停、可重复生成和漂移门禁。"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / 'scripts/export_openapi.py'


def export(target, *options, env=None):
    result = subprocess.run([sys.executable, str(EXPORT), '--output', str(target), *options],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90,
                            env={**os.environ, 'PYTHONUTF8': '1', **(env or {})})
    assert result.returncode == 0, result.stderr
    return json.loads(target.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def full(tmp_path_factory):
    folder = tmp_path_factory.mktemp('sdk-export')
    first = folder / 'full.json'
    schema = export(first)
    return folder, first, schema


def test_all_registered_routes_and_response_fields_are_present(full):
    _, _, schema = full
    for path in ['/api/v1/tasks/backups/', '/api/v1/files/', '/api/v1/ip-policy/',
                 '/api/v1/feature-flags/flags/', '/api/v1/auth/login/',
                 '/api/v1/reports/definitions/', '/api/v1/reports/definitions/{id}/run/']:
        assert path in schema['paths']
    status = schema['components']['schemas']['BackupStatus']
    assert status['properties']['restore_requests']['items']['$ref'].endswith('/BackupRestoreHistory')
    operations = [operation['operationId'] for row in schema['paths'].values()
                  for method, operation in row.items() if method in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}]
    assert len(operations) == len(set(operations))
    assert len(schema['info']['x-admincore-modules']) >= 13
    for path in ('/api/v1/permissions/permissions/', '/api/v1/permissions/permissions/{id}/'):
        methods = set(schema['paths'][path]) & {'get', 'post', 'put', 'patch', 'delete'}
        assert methods == {'get'}, '权限定义目录必须只读，SDK不应发布不可调用的写操作'


def test_export_is_deterministic_and_ignores_deployment_environment(full):
    folder, first, _ = full
    second = folder / 'repeat.json'
    sentinel = 'synthetic-invalid-config-not-a-secret'
    export(second, env={'ADMINCORE_MODULES': sentinel, 'DJANGO_ENV': 'production',
        'DB_HOST': 'unreachable.invalid', 'AUTH_TOTP_ENCRYPTION_KEY': sentinel,
        'ADMINCORE_FIELD_ENCRYPTION_ENABLED': 'True', 'ADMINCORE_API_LIFECYCLE': sentinel})
    assert first.read_bytes() == second.read_bytes()
    assert sentinel not in second.read_text(encoding='utf-8')


def test_minimal_and_selected_modules_use_real_url_configuration(full):
    folder, _, _ = full
    minimal = export(folder / 'minimal.json', '--profile', 'minimal')
    assert minimal['info']['x-admincore-modules'] == []
    assert '/api/v1/auth/login/' in minimal['paths']
    assert not any(path.startswith(('/api/v1/tasks/', '/api/v1/files/', '/api/v1/ip-policy/')) for path in minimal['paths'])
    selected = export(folder / 'selected.json', '--modules', 'files')
    assert selected['info']['x-admincore-modules'] == ['files']
    assert '/api/v1/files/' in selected['paths'] and '/api/v1/tasks/backups/' not in selected['paths']


def test_unknown_module_is_rejected_before_export(full):
    folder, _, _ = full
    target = folder / 'invalid.json'
    result = subprocess.run([sys.executable, str(EXPORT), '--modules', 'unregistered', '--output', str(target)],
                            cwd=ROOT, capture_output=True, timeout=30)
    assert result.returncode != 0 and not target.exists()


def test_generator_check_detects_type_and_schema_drift(tmp_path):
    node = os.getenv('ADMINCORE_NODE', 'node')
    script = ROOT / 'frontend/scripts/generate-sdk.mjs'
    def generate(check=False):
        return subprocess.run([node, str(script), '--profile', 'minimal', '--output-dir', str(tmp_path),
                               *(['--check'] if check else [])], cwd=ROOT / 'frontend', capture_output=True,
                              text=True, encoding='utf-8', timeout=90)
    assert generate().returncode == 0
    assert generate(check=True).returncode == 0
    target = tmp_path / 'schema.ts'
    original = target.read_bytes()
    target.write_bytes(original + b'// synthetic drift\n')
    failed = generate(check=True)
    assert failed.returncode != 0 and 'SDK contract drift' in failed.stderr
    target.write_bytes(original)
    target = tmp_path / 'openapi.json'
    target.write_bytes(target.read_bytes() + b'\n')
    assert generate(check=True).returncode != 0
    assert generate().returncode == 0
    target = tmp_path / 'routes.ts'
    target.write_bytes(target.read_bytes() + b'// synthetic route drift\n')
    assert generate(check=True).returncode != 0
