"""在独立临时 PostgreSQL 验证 IP 策略与跨连接版本竞争，不加载项目凭据。"""
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
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'ip_policy',
        'USER': 'postgres', 'PASSWORD': os.environ['IP_POLICY_PG_PASSWORD'],
        'HOST': '127.0.0.1', 'PORT': os.environ['IP_POLICY_PG_PORT']}}
    import pytest
    os.chdir(ROOT / 'backend')
    return pytest.main(['-q', '--tb=short', 'tests/test_ip_policy.py'])


def main():
    name = 'admincore-ip-policy-' + uuid.uuid4().hex[:8]
    folder = ROOT / '.codex-validation' / name
    folder.mkdir(parents=True)
    environment = {**os.environ, 'PYTHON_DOTENV_DISABLED': '1', 'PYTHONUTF8': '1', 'IP_POLICY_PG_PASSWORD': secrets.token_urlsafe(32)}
    environment['POSTGRES_PASSWORD'] = environment['IP_POLICY_PG_PASSWORD']
    def docker(*args, check=True):
        result = subprocess.run(['docker', *args], env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        if check and result.returncode:
            raise RuntimeError('隔离 PostgreSQL 操作失败：' + name)
        return result
    docker('run', '-d', '--name', name, '--label', 'admincore.validation=ip-policy',
           '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=ip_policy', '-p', '127.0.0.1::5432',
           '--tmpfs', '/var/lib/postgresql', 'postgres:18.6')
    try:
        port = docker('port', name, '5432/tcp').stdout.strip().rsplit(':', 1)[1]
        environment['IP_POLICY_PG_PORT'] = port
        for _ in range(60):
            if docker('exec', name, 'pg_isready', '-U', 'postgres', check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('隔离 PostgreSQL 启动超时')
        with (folder / 'pytest.log').open('w', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, __file__, '--worker'], env=environment, stdout=log, stderr=subprocess.STDOUT)
        (folder / 'report.json').write_text(json.dumps({'postgres': '18.6', 'passed': result.returncode == 0, 'evidence': 'pytest.log'}, indent=2), encoding='utf-8')
        if result.returncode:
            raise RuntimeError('IP 策略回归失败，保留容器和证据：' + str(folder))
        docker('rm', '-f', name)
        print('独立 PostgreSQL IP 策略回归通过；已移除容器并释放端口 ' + port + '；证据：' + str(folder))
    except Exception:
        print('保留诊断容器：' + name, file=sys.stderr)
        raise


if __name__ == '__main__':
    sys.exit(worker() if '--worker' in sys.argv else main())
