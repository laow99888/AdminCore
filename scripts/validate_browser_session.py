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


def run(arguments, *, input=None, allowed_failure=False):
    result = subprocess.run(arguments, cwd=ROOT, input=input, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=360)
    with (FOLDER / 'contract.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('浏览器会话验收失败，见 contract.log')
    return result


def compose(*args, input=None, allowed_failure=False):
    command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env'),
               '-f', 'docker-compose.yml', '-f', 'compose.minimal.yml', '-f', 'compose.realtime.yml',
               '-f', str(FOLDER / 'override.yml')]
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
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', PORT))
    FOLDER.mkdir(parents=True)
    password = secrets.token_urlsafe(40)
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
                   'DB_NAME': 'browser_session_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
                   'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
                   'DJANGO_DEBUG': 'False', 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False', 'USE_TLS': 'True',
                   'AUTH_BROWSER_COOKIE_ENABLED': 'True', 'ALLOW_PUBLIC_REGISTRATION': 'False'}
    environment['AUTH_TOTP_ENCRYPTION_KEY'] = Fernet.generate_key().decode('ascii')
    env_file = FOLDER / 'fixture.env'
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    (FOLDER / 'override.yml').write_text(f'''services:
  backend:
    image: {PROJECT}-backend
    environment:
      ADMINCORE_MODULES: realtime
    ports: !reset []
    env_file: !override
      - "{env_file.as_posix()}"
  realtime:
    image: {PROJECT}-backend
    env_file: !override
      - "{env_file.as_posix()}"
    environment:
      ADMINCORE_PRESET: minimal
      ADMINCORE_MODULES: realtime
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
    report = {'passed': False, 'project': PROJECT, 'ports': [PORT]}
    try:
        compose('build', 'backend', 'frontend')
        compose('up', '-d', '--wait', '--wait-timeout', '150', 'db', 'backend', 'frontend', 'realtime')
        for local, remote in [('https.conf', '/etc/nginx/conf.d/default.conf'), ('tls.crt', '/etc/nginx/tls.crt'),
                              ('tls.key', '/etc/nginx/tls.key')]:
            compose('cp', str(FOLDER / local), 'frontend:' + remote)
        compose('exec', '-T', 'frontend', 'nginx', '-t')
        compose('exec', '-T', 'frontend', 'nginx', '-s', 'reload')
        # 初始化强制改密已另有真实回归；这里允许进入业务页以验证 Cookie 生命周期。
        setup = """import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django; django.setup()
from django.conf import settings
assert settings.DATABASES['default']['NAME'] == 'browser_session_fixture'
from django.contrib.auth import get_user_model
get_user_model().objects.filter(username='admin').update(must_change_password=False)
get_user_model().objects.create_superuser('mobile-admin', password=os.environ['ADMINCORE_ADMIN_PASSWORD'], must_change_password=False)
"""
        compose('exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=setup)
        (FOLDER / 'browser-access.json').write_text(json.dumps({'password': password}), encoding='utf-8')
        bundled = ROOT / '.codex-validation/toolchains/node-v24.21.0-win-x64/node.exe'
        node = str(bundled) if os.name == 'nt' and bundled.exists() else shutil.which('node')
        if not node:
            raise RuntimeError('需要 Node.js 和已安装的 Playwright Chromium')
        run([node, str(ROOT / 'scripts/browser_session_browser.mjs'), str(ROOT / 'frontend'), str(FOLDER), str(PORT)])
        report['browser'] = json.loads((FOLDER / 'browser-report.json').read_text(encoding='utf-8'))
        report['passed'] = True
    finally:
        if report['passed']:
            compose('down', '-v', '--remove-orphans')
            run(['docker', 'image', 'rm', PROJECT + '-backend', PROJECT + '-frontend'])
            for name in ['fixture.env', 'browser-access.json', 'tls.key', 'tls.crt']:
                (FOLDER / name).unlink(missing_ok=True)
            report['cleaned'] = ['隔离容器、卷、镜像标签', '测试凭据及TLS私钥/证书']
        else:
            compose('logs', '--no-color', allowed_failure=True)
            compose('stop', allowed_failure=True)
        (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(FOLDER), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
