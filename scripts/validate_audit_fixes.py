"""在独立 PostgreSQL 18.6 容器中验证集中审查修复，不加载工作区环境或访问业务库。"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def worker():
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.testing'
    from django.conf import settings
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'audit_fixes', 'USER': 'postgres', 'PASSWORD': os.environ['AUDIT_FIX_PG_PASSWORD'],
        'HOST': '127.0.0.1', 'PORT': os.environ['AUDIT_FIX_PG_PORT']}}
    import pytest
    os.chdir(ROOT / 'backend')
    return pytest.main(['-q', '--tb=short', 'tests/test_audit_fix_lifecycle.py',
                       'tests/test_audit_fix_contracts.py', 'tests/test_audit_fix_storage_outbox.py',
                       'tests/test_tenant_object_contract.py', 'tests/test_multi_tenant.py',
                       'tests/test_advanced_approvals.py',
                       'tests/test_reports.py',
                       'tests/test_task_reliability.py::test_terminal_import_summary_uses_committed_receipts',
                       'tests/test_api_credentials.py::test_disabled_then_reenabled_owner_never_revives_old_api_secret'])


def main():
    name = 'admincore-audit-fixes-' + uuid.uuid4().hex[:8]
    folder = ROOT / '.codex-validation' / name
    folder.mkdir(parents=True)
    environment = {**os.environ, 'PYTHON_DOTENV_DISABLED': '1', 'PYTHONUTF8': '1',
                   'AUDIT_FIX_PG_PASSWORD': secrets.token_urlsafe(32)}
    def docker(*args, check=True):
        result = subprocess.run(['docker', *args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        if check and result.returncode:
            raise RuntimeError('隔离 PostgreSQL 操作失败，容器：' + name)
        return result
    # 密码仅经子进程环境传入，不写报告或命令参数。
    environment['POSTGRES_PASSWORD'] = environment['AUDIT_FIX_PG_PASSWORD']
    result = subprocess.run(['docker', 'run', '-d', '--name', name, '--label', 'admincore.validation=audit-fixes',
        '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=audit_fixes', '-p', '127.0.0.1::5432',
        '--tmpfs', '/var/lib/postgresql', 'postgres:18.6'], env=environment, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError('隔离容器启动失败')
    try:
        port = docker('port', name, '5432/tcp').stdout.strip().rsplit(':', 1)[1]
        environment['AUDIT_FIX_PG_PORT'] = port
        for _ in range(60):
            if docker('exec', name, 'pg_isready', '-U', 'postgres', check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('隔离 PostgreSQL 启动超时')
        with (folder / 'pytest.log').open('w', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, __file__, '--worker'], env=environment, stdout=log, stderr=subprocess.STDOUT)
        (folder / 'report.json').write_text(json.dumps({'postgres': '18.6', 'passed': result.returncode == 0,
            'evidence': 'pytest.log'}, indent=2), encoding='utf-8')
        if result.returncode:
            raise RuntimeError('回归失败，保留容器和证据：' + str(folder))
        docker('rm', '-f', name)
        print('独立 PostgreSQL 回归通过，已移除容器并释放端口 ' + port + '；证据：' + str(folder))
    except Exception:
        print('保留诊断容器：' + name, file=sys.stderr)
        raise


if __name__ == '__main__':
    sys.exit(worker() if '--worker' in sys.argv else main())
