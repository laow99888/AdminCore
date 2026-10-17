"""使用独立 PostgreSQL/Redis 和产品构建验收 P2 设计器；不连接已有站点。"""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-p2-pages-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
PORT = 18495


def run(arguments, *, input=None, allowed_failure=False):
    result = subprocess.run(arguments, cwd=ROOT, input=input, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=360)
    with (FOLDER / 'private.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('P2 浏览器验收失败，见私有日志')
    return result


def compose(*args, input=None, allowed_failure=False):
    return run(['docker', 'compose', '-p', PROJECT, '--profile', 'optional', '--env-file', str(FOLDER / 'fixture.env'),
                '-f', 'docker-compose.yml', '-f', 'compose.minimal.yml', '-f', str(FOLDER / 'override.yml'), *args],
               input=input, allowed_failure=allowed_failure)


def sql(source):
    prefix = "import django; django.setup()\nfrom django.conf import settings\nassert settings.DATABASES['default']['NAME'] == 'p2_browser_fixture'\n"
    return compose('exec', '-T', 'backend', 'python', '-c',
                   "import os,sys; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); exec(sys.stdin.read())", input=prefix + source)


def main():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', PORT))
    FOLDER.mkdir(parents=True)
    password = secrets.token_urlsafe(40)
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
                   'DB_NAME': 'p2_browser_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
                   'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
                   'DJANGO_DEBUG': 'False', 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False', 'USE_TLS': 'False',
                   'AUTH_BROWSER_COOKIE_ENABLED': 'False', 'ALLOW_PUBLIC_REGISTRATION': 'False'}
    env_file = FOLDER / 'fixture.env'
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    (FOLDER / 'override.yml').write_text(f'''services:
  backend:
    image: {PROJECT}-backend
    environment:
      ADMINCORE_MODULES: notifications,approvals,online_forms,reports
    ports: !reset []
    env_file: !override
      - "{env_file.as_posix()}"
  worker:
    env_file: !override
      - "{env_file.as_posix()}"
  beat:
    env_file: !override
      - "{env_file.as_posix()}"
  frontend:
    image: {PROJECT}-frontend
    build:
      context: ./frontend
      args:
        VITE_AUTH_SESSION_TRANSPORT: bearer
    ports: !override
      - "127.0.0.1:{PORT}:80"
''', encoding='utf-8')
    report = {'passed': False, 'project': PROJECT, 'ports': [PORT]}
    try:
        compose('build', 'backend', 'frontend')
        compose('up', '-d', '--wait', '--wait-timeout', '150', 'db', 'redis', 'backend', 'frontend')
        result = sql("""from django.contrib.auth import get_user_model
from apps.tasks.models import TaskRecord
User = get_user_model()
User.objects.filter(username='admin').update(must_change_password=False)
mobile = User.objects.create_superuser('mobile-admin', password=__import__('os').environ['ADMINCORE_ADMIN_PASSWORD'], must_change_password=False)
admin = User.objects.get(username='admin')
for index, status in enumerate(('pending', 'pending', 'success')):
    TaskRecord.objects.create(creator=admin, name='aggregate-fixture', status=status, progress=(index+1)*10)
print(__import__('json').dumps({'desktop': str(admin.pk), 'mobile': str(mobile.pk)}))
""")
        (FOLDER / 'browser-access.json').write_text(json.dumps({'password': password, 'users': json.loads(result.stdout)}), encoding='utf-8')
        bundled = ROOT / '.codex-validation/toolchains/node-v24.21.0-win-x64/node.exe'
        node = str(bundled) if os.name == 'nt' and bundled.exists() else shutil.which('node')
        if not node:
            raise RuntimeError('需要 Node.js 和 Playwright Chromium')
        run([node, str(ROOT / 'scripts/p2_pages_browser.mjs'), str(ROOT / 'frontend'), str(FOLDER), str(PORT)])
        report['browser'] = json.loads((FOLDER / 'browser-report.json').read_text(encoding='utf-8'))
        sql("""from apps.approvals.models import ApprovalFlow
from apps.online_forms.models import OnlineForm, OnlineFormRecord
from apps.reports.models import ReportDefinition
assert ApprovalFlow.objects.filter(status='published').count() == 2
assert OnlineForm.objects.filter(status='published').count() == 2
assert OnlineFormRecord.objects.count() == 2
assert all(row.data == {'title': '实际填写'} for row in OnlineFormRecord.objects.all())
assert ReportDefinition.objects.filter(status='published').count() == 2
print('P2 SQL: published definitions and submitted records verified')
""")
        report['passed'] = True
    finally:
        try:
            if report['passed']:
                compose('down', '-v', '--remove-orphans')
                run(['docker', 'image', 'rm', PROJECT + '-backend', PROJECT + '-frontend'])
                for name in ['fixture.env', 'browser-access.json']:
                    (FOLDER / name).unlink(missing_ok=True)
                report['cleaned'] = ['隔离容器/卷/网络/镜像标签及测试凭据']
            else:
                compose('logs', '--no-color', allowed_failure=True)
                compose('stop', allowed_failure=True)
        except Exception:
            report['passed'] = False
            report['cleanup_failed'] = True
            compose('stop', allowed_failure=True)
            raise
        finally:
            (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'evidence': str(FOLDER), **report}, ensure_ascii=False), flush=True)



if __name__ == '__main__':
    main()
