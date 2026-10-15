"""真实 PostgreSQL/Nginx 生命周期通知验收；只操作随机命名的隔离项目。"""
from pathlib import Path
import hashlib
import json
import secrets
import socket
import subprocess
import time
import uuid

import requests

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-api-lifecycle-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
PORTS = [18480, 18481]
BASE = 'http://127.0.0.1:18481'
CHECKS = []
PLANS = {
    'default': {},
    'scheduled': {'v1': {'deprecated_at': '2099-01-01T00:00:00Z', 'sunset_at': '2099-04-01T00:00:00Z', 'migration_url': '/api/versions/'}},
    'past': {'v1': {'deprecated_at': '2020-01-01T00:00:00Z', 'sunset_at': '2020-04-01T00:00:00Z', 'migration_url': '/api/versions/'}},
}


def run(arguments, *, input=None, allowed_failure=False):
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, input=input,
        encoding='utf-8', errors='replace', timeout=360)
    with (FOLDER / 'docker.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('隔离命令失败，见 docker.log')
    return result


def compose(mode, *arguments, input=None, allowed_failure=False):
    command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env')]
    for path in ['docker-compose.yml', 'compose.minimal.yml', str(FOLDER / 'override.yml'), str(FOLDER / (mode + '.yml'))]:
        command += ['-f', path]
    return run(command + list(arguments), input=input, allowed_failure=allowed_failure)


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)
    print('通过：' + label, flush=True)


def api(path, *, token=None, method='GET', expected=200, **kwargs):
    headers = kwargs.pop('headers', {})
    response = requests.request(method, BASE + path,
        headers={**({'Authorization': 'Bearer ' + token} if token else {}), **headers}, timeout=15, **kwargs)
    if response.status_code != expected:
        raise AssertionError(method + ' ' + path + ' 预期 ' + str(expected) + ' 实际 ' + str(response.status_code))
    return response


def ready():
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            if requests.get(BASE + '/api/v1/health/', timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.3)
    raise RuntimeError('隔离入口未恢复就绪')


def snippet(mode, code):
    prefix = "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); import django; django.setup(); from django.conf import settings; assert settings.DATABASES['default']['NAME']=='api_lifecycle_fixture'\n"
    return compose(mode, 'exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=prefix + code).stdout.strip()


def main():
    for port in PORTS:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password, new_password = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    env_file = FOLDER / 'fixture.env'
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'api_lifecycle_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
        'DJANGO_DEBUG': 'False', 'BACKEND_PORT': str(PORTS[0]), 'FRONTEND_PORT': str(PORTS[1]),
        'AUTH_LOGIN_CAPTCHA_ENABLED': 'False', 'USE_TLS': 'False',
        'CORS_ALLOWED_ORIGINS': 'https://client.example'}
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    override = 'services:\n'
    for service in ['backend', 'worker', 'beat']:
        override += f'  {service}:\n    env_file: !override\n      - "{env_file.as_posix()}"\n    image: {PROJECT}-backend\n'
    override += f'  frontend:\n    image: {PROJECT}-frontend\n    ports: !override\n      - "127.0.0.1:{PORTS[1]}:80"\n'
    (FOLDER / 'override.yml').write_text(override, encoding='utf-8')
    for mode, plan in PLANS.items():
        (FOLDER / (mode + '.yml')).write_text('services:\n  backend:\n    environment:\n      ADMINCORE_MODULES: files\n      ADMINCORE_API_LIFECYCLE: ' + json.dumps(json.dumps(plan, separators=(',', ':'))) + '\n', encoding='utf-8')
    report = {'passed': False, 'project': PROJECT, 'ports': PORTS}
    mode = 'default'
    try:
        compose(mode, 'build', 'backend', 'frontend')
        compose(mode, 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'backend', 'frontend')
        ready()
        check('真实生产三服务入口，无 Redis/worker/beat', set(compose(mode, 'ps', '--status', 'running', '--services').stdout.split()) == {'db', 'backend', 'frontend'})
        token = api('/api/v1/auth/login/', method='POST', json={'username': 'admin', 'password': password}).json()['access']
        api('/api/v1/auth/change_password/', token=token, method='POST', json={'old_password': password, 'new_password': new_password, 'new_password2': new_password})
        token = api('/api/v1/auth/login/', method='POST', json={'username': 'admin', 'password': new_password}).json()['access']
        content = b'API lifecycle original private file\n' * 12000
        file_id = api('/api/v1/files/', method='POST', token=token, expected=201,
            files={'file': ('original.txt', content, 'text/plain')}).json()['id']
        stable = snippet(mode, "from django.contrib.auth import get_user_model; from apps.permissions.models import Permission; from apps.files.models import FileModel; import hashlib,json; print(hashlib.sha256(json.dumps({'users':list(get_user_model().objects.order_by('id').values('id','username','password','is_active')), 'permissions':list(Permission.objects.order_by('id').values('id','code')), 'files':list(FileModel.objects.order_by('id').values('id','md5','size','original_name'))},default=str,sort_keys=True).encode()).hexdigest())")
        for mode in ['default', 'scheduled', 'past', 'default']:
            compose(mode, 'up', '-d', '--wait', '--wait-timeout', '150', 'backend')
            ready()
            health = api('/api/v1/health/')
            metadata = api('/api/versions/?password=not-a-real-secret')
            version = metadata.json()['versions'][0]
            expected_status = {'default': 'active', 'scheduled': 'scheduled', 'past': 'sunset_due'}[mode]
            check(mode + '：公开版本状态、90天策略及禁止缓存一致', version['status'] == expected_status
                and metadata.json()['minimum_compatibility_days'] == 90 and metadata.json()['automatic_retirement'] is False
                and metadata.headers['Cache-Control'] == 'no-store' and 'not-a-real-secret' not in metadata.text)
            check(mode + '：HEAD 无正文，生产 CSRF 拒绝匿名 POST', not api('/api/versions/', method='HEAD').content
                and api('/api/versions/', method='POST', expected=403).status_code == 403)
            check(mode + '：已登记版本标识且默认无废弃通知', health.headers['X-API-Version'] == 'v1'
                and ('Deprecation' in health.headers) == bool(PLANS[mode])
                and ('Sunset' in health.headers) == bool(PLANS[mode]))
            if PLANS[mode]:
                check(mode + '：标准日期头和迁移链接原样穿过 Nginx', health.headers['Deprecation'].startswith('@')
                    and health.headers['Sunset'].endswith(' GMT') and health.headers['Link'] == '</api/versions/>; rel="deprecation"')
            private = api('/api/v1/users/', expected=401)
            allowed = api('/api/v1/users/', token=token)
            check(mode + '：切换保留登录，匿名仍拒绝，私有响应仍禁止缓存', private.headers['X-API-Version'] == 'v1'
                and allowed.headers['Cache-Control'] == 'private, no-store')
            check(mode + '：未登记版本不冒充 v1，未知 v1 路由保留通知',
                'X-API-Version' not in api('/api/v2/health/', expected=404).headers
                and api('/api/v1/does-not-exist/', expected=404).headers['X-API-Version'] == 'v1')
            check(mode + '：规范路径重定向仍带版本通知',
                api('/api/v1/health', expected=301, allow_redirects=False).headers['X-API-Version'] == 'v1')
            api('/api/v1/tasks/', token=token, expected=404)
            schema = api('/api/v1/schema/', token=token, headers={'Accept': 'application/json'}).json()
            operation = schema['paths']['/api/v1/users/']['get']
            check(mode + '：OpenAPI 状态、响应头、JWT 认证契约一致', operation.get('deprecated', False) == (mode == 'past')
                and operation['x-api-lifecycle'] == version
                and ('Deprecation' in operation['responses']['200']['headers']) == bool(PLANS[mode])
                and 'jwtAuth' in schema['components']['securitySchemes'])
            download = api('/api/v1/files/' + file_id + '/download/', token=token)
            check(mode + '：真实私有流式下载正文、文件名和安全头不变', hashlib.sha256(download.content).digest() == hashlib.sha256(content).digest()
                and 'original.txt' in download.headers['Content-Disposition']
                and download.headers['X-Content-Type-Options'] == 'nosniff'
                and ('Deprecation' in download.headers) == bool(PLANS[mode]))
            cors = api('/api/v1/health/', headers={'Origin': 'https://client.example'})
            check(mode + '：CORS 仅允许既有来源并暴露生命周期头', cors.headers.get('Access-Control-Allow-Origin') == 'https://client.example'
                and {'Deprecation', 'Sunset', 'Link', 'X-API-Version'} <= set(cors.headers['Access-Control-Expose-Headers'].split(', '))
                and 'Access-Control-Allow-Origin' not in api('/api/v1/health/', headers={'Origin': 'https://attacker.example'}).headers)
            check(mode + '：管理员、权限和原文件在配置切换后保持一致', stable == snippet(mode, "from django.contrib.auth import get_user_model; from apps.permissions.models import Permission; from apps.files.models import FileModel; import hashlib,json; print(hashlib.sha256(json.dumps({'users':list(get_user_model().objects.order_by('id').values('id','username','password','is_active')), 'permissions':list(Permission.objects.order_by('id').values('id','code')), 'files':list(FileModel.objects.order_by('id').values('id','md5','size','original_name'))},default=str,sort_keys=True).encode()).hexdigest())"))
        compose(mode, 'exec', '-T', 'backend', 'python', 'manage.py', 'spectacular', '--validate', '--fail-on-warn', '--file', '/tmp/lifecycle-schema.yml')
        check('实际生产 OpenAPI 校验无警告', True)
        report['passed'] = True
    finally:
        report['checks'] = CHECKS
        if report['passed']:
            compose(mode, 'down', '-v', '--remove-orphans')
            env_file.unlink()
            report['cleaned'] = ['isolated containers and volumes', str(env_file)]
        else:
            compose(mode, 'logs', '--no-color', allowed_failure=True)
        (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(FOLDER), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
