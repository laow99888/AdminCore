"""隔离 HTTPS/PostgreSQL/Nginx 验收浏览器 Cookie；不连接任何已有站点。"""
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import uuid

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-browser-session-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
PORT = 18493
OIDC_PORT = 18494


def run(arguments, *, input=None, allowed_failure=False):
    result = subprocess.run(arguments, cwd=ROOT, input=input, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=360)
    with (FOLDER / 'contract.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('浏览器会话验收失败，见 contract.log')
    return result


def compose(*args, input=None, allowed_failure=False):
    command = ['docker', 'compose', '-p', PROJECT, '--profile', 'optional', '--env-file', str(FOLDER / 'fixture.env'),
               '-f', 'docker-compose.yml', '-f', 'compose.minimal.yml', '-f', 'compose.realtime.yml',
               '-f', str(FOLDER / 'override.yml')]
    if (FOLDER / 'oidc.yml').exists():
        command += ['-f', str(FOLDER / 'oidc.yml')]
    return run(command + list(args), input=input, allowed_failure=allowed_failure)


def certificate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),
                           x509.IPAddress(ip_address('127.0.0.1'))]), critical=False).sign(key, hashes.SHA256()))
    (FOLDER / 'tls.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (FOLDER / 'tls.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def main():
    for port in (PORT, OIDC_PORT):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password = secrets.token_urlsafe(40)
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
                   'DB_NAME': 'browser_session_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
                   'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
                   'DJANGO_DEBUG': 'False', 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False', 'USE_TLS': 'True',
                   'AUTH_BROWSER_COOKIE_ENABLED': 'True', 'ALLOW_PUBLIC_REGISTRATION': 'False'}
    environment['AUTH_TOTP_ENCRYPTION_KEY'] = Fernet.generate_key().decode('ascii')
    issuer = f'https://127.0.0.1:{OIDC_PORT}'
    environment.update({
        'SSO_ISSUER': issuer, 'SSO_AUTHORIZATION_ENDPOINT': issuer + '/authorize',
        'SSO_TOKEN_ENDPOINT': issuer + '/token', 'SSO_JWKS_URI': issuer + '/jwks',
        'SSO_CLIENT_ID': 'browser-fixture', 'SSO_CLIENT_SECRET': secrets.token_urlsafe(40),
        'SSO_ENCRYPTION_KEY': Fernet.generate_key().decode('ascii'),
        'SSO_REDIRECT_URI': f'https://127.0.0.1:{PORT}/api/v1/sso/callback/',
        'SSO_FRONTEND_ORIGIN': f'https://127.0.0.1:{PORT}',
    })
    env_file = FOLDER / 'fixture.env'
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    (FOLDER / 'override.yml').write_text(f'''services:
  backend:
    image: {PROJECT}-backend
    environment:
      ADMINCORE_MODULES: realtime,sso
    ports: !reset []
    env_file: !override
      - "{env_file.as_posix()}"
  realtime:
    image: {PROJECT}-backend
    env_file: !override
      - "{env_file.as_posix()}"
    environment:
      ADMINCORE_PRESET: minimal
      ADMINCORE_MODULES: realtime,sso
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
        VITE_AUTH_SESSION_TRANSPORT: cookie
    ports: !override
      - "127.0.0.1:{PORT}:443"
''', encoding='utf-8')
    certificate()
    config = (ROOT / 'frontend/nginx.conf').read_text(encoding='utf-8')
    config = config.replace('${TRUSTED_PROXY_IP}', '127.0.0.1').replace('${REALTIME_UPSTREAM}', 'realtime:8000')
    config = config.replace('listen 80;', 'listen 443 ssl;\n    ssl_certificate /etc/nginx/tls.crt;\n    ssl_certificate_key /etc/nginx/tls.key;')
    (FOLDER / 'https.conf').write_text(config, encoding='utf-8')
    report = {'passed': False, 'project': PROJECT, 'ports': [PORT, OIDC_PORT]}
    try:
        compose('build', 'backend', 'frontend')
        # 构建上下文只有无凭据的夹具源码，不包含同目录测试 env 或私钥。
        build_context = FOLDER / 'oidc-build'
        build_context.mkdir()
        for name in ['browser_oidc_fixture.py', 'browser_oidc_settings.py']:
            shutil.copyfile(ROOT / 'scripts' / name, build_context / name)
        (build_context / 'Dockerfile').write_text(
            f'FROM {PROJECT}-backend\nCOPY --chown=10001:10001 browser_oidc_fixture.py browser_oidc_settings.py /app/\n',
            encoding='utf-8')
        run(['docker', 'build', '-t', PROJECT + '-oidc', str(build_context)])
        (FOLDER / 'oidc.yml').write_text(f'''services:
  backend:
    image: {PROJECT}-oidc
    environment:
      DJANGO_SETTINGS_MODULE: browser_oidc_settings
      SSL_CERT_FILE: /tmp/oidc-ca.crt
    ports: !override
      - "127.0.0.1:{OIDC_PORT}:{OIDC_PORT}"
  realtime:
    image: {PROJECT}-oidc
    environment:
      DJANGO_SETTINGS_MODULE: browser_oidc_settings
      SSL_CERT_FILE: /tmp/oidc-ca.crt
''', encoding='utf-8')
        compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '150', 'db', 'redis', 'backend', 'frontend', 'realtime')
        for local, remote in [('https.conf', '/etc/nginx/conf.d/default.conf'), ('tls.crt', '/etc/nginx/tls.crt'),
                              ('tls.key', '/etc/nginx/tls.key')]:
            compose('cp', str(FOLDER / local), 'frontend:' + remote)
        compose('exec', '-T', 'frontend', 'nginx', '-t')
        compose('exec', '-T', 'frontend', 'nginx', '-s', 'reload')
        compose('cp', str(FOLDER / 'tls.crt'), 'backend:/tmp/oidc-ca.crt')
        compose('cp', str(FOLDER / 'tls.key'), 'backend:/tmp/oidc.key')
        # Docker cp 不支持只读根文件系统；通过容器内进程写入允许的 /tmp tmpfs。
        compose('exec', '-T', 'realtime', 'python', '-c',
                "import sys; from pathlib import Path; Path('/tmp/oidc-ca.crt').write_text(sys.stdin.read())",
                input=(FOLDER / 'tls.crt').read_text())
        compose('exec', '-d', 'backend', 'python', '/app/browser_oidc_fixture.py')
        ready = """import time, urllib.request
for attempt in range(30):
    try:
        assert urllib.request.urlopen('https://127.0.0.1:18494/health', timeout=2).status == 200
        break
    except OSError:
        time.sleep(.2)
else:
    raise RuntimeError('Isolated HTTPS provider did not start')
"""
        compose('exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=ready)
        # 初始化强制改密已另有真实回归；这里允许进入业务页以验证 Cookie 生命周期。
        setup = """import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django; django.setup()
from django.conf import settings
assert settings.DATABASES['default']['NAME'] == 'browser_session_fixture'
from django.contrib.auth import get_user_model
get_user_model().objects.filter(username='admin').update(must_change_password=False)
get_user_model().objects.create_superuser('mobile-admin', password=os.environ['ADMINCORE_ADMIN_PASSWORD'], must_change_password=False)
from apps.sso.models import ExternalIdentity
for subject in ('desktop', 'mobile'):
    user = get_user_model().objects.create_superuser('sso-' + subject, password=os.environ['ADMINCORE_ADMIN_PASSWORD'], must_change_password=False)
    ExternalIdentity.objects.create(user=user, issuer=settings.SSO_ISSUER, subject=subject)
"""
        compose('exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=setup)
        (FOLDER / 'browser-access.json').write_text(json.dumps({'password': password}), encoding='utf-8')
        bundled = ROOT / '.codex-validation/toolchains/node-v24.21.0-win-x64/node.exe'
        node = str(bundled) if os.name == 'nt' and bundled.exists() else shutil.which('node')
        if not node:
            raise RuntimeError('需要 Node.js 和已安装的 Playwright Chromium')
        run([node, str(ROOT / 'scripts/browser_session_browser.mjs'), str(ROOT / 'frontend'), str(FOLDER), str(PORT)])
        report['browser'] = json.loads((FOLDER / 'browser-report.json').read_text(encoding='utf-8'))
        # 独立套件共用来源 IP；只在套件之间重置专用 Redis 的限流计数。
        # 不修改产品阈值，也不在任何单次登录或重放检查期间重置。
        reset = """import django; django.setup()
from django.conf import settings
assert settings.DATABASES['default']['NAME'] == 'browser_session_fixture'
assert settings.CACHES['default']['LOCATION'] == 'redis://redis:6379/0'
from django.core.cache import cache
cache.clear()
"""
        sso_results = []
        for device in ('desktop', 'mobile'):
            compose('exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=reset)
            run([node, str(ROOT / 'scripts/browser_sso_session.mjs'), str(ROOT / 'frontend'), str(FOLDER), str(PORT), str(OIDC_PORT), device])
            sso_results.append(json.loads((FOLDER / f'sso-browser-{device}-report.json').read_text(encoding='utf-8')))
        report['sso_browser'] = {'passed': all(item['passed'] for item in sso_results),
                                'checks': [check for item in sso_results for check in item['checks']],
                                'provider': sso_results[-1]['provider']}
        (FOLDER / 'sso-browser-report.json').write_text(json.dumps(report['sso_browser'], ensure_ascii=False, indent=2), encoding='utf-8')
        verify = """import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django; django.setup()
from django.conf import settings
assert settings.DATABASES['default']['NAME'] == 'browser_session_fixture'
from apps.sso.models import LoginFlow, SSOSession
assert SSOSession.objects.count() == 2
assert not SSOSession.objects.filter(session__revoked_at__isnull=True).exists()
assert LoginFlow.objects.filter(completed_at__isnull=False, completion_digest='').count() >= 2
print('SSO SQL: two linked sessions revoked and completion secrets cleared')
"""
        compose('exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=verify)
        report['passed'] = True
    finally:
        try:
            if report['passed']:
                compose('down', '-v', '--remove-orphans')
                run(['docker', 'image', 'rm', PROJECT + '-oidc', PROJECT + '-backend', PROJECT + '-frontend'])
                for name in ['fixture.env', 'browser-access.json', 'tls.key', 'tls.crt']:
                    (FOLDER / name).unlink(missing_ok=True)
                report['cleaned'] = ['隔离容器、卷、镜像标签', '测试凭据及TLS私钥/证书']
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
