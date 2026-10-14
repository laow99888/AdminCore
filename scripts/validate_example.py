"""实际 PostgreSQL/Nginx 示例模块启停、版本/幂等/审计和并发验收。

不读取正式凭据，不连接正式库。成功只清理本脚本创建的项目和凭据；失败保留证据。
"""
from pathlib import Path
import json
import secrets
import socket
import subprocess
import time
import uuid
import requests

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-example-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
PORTS = [18440, 18441]
BASE = 'http://127.0.0.1:18441/api/v1/'
CHECKS = []


def run(arguments, *, input=None, allowed_failure=False):
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, input=input,
        encoding='utf-8', errors='replace', timeout=360)
    with (FOLDER / 'docker.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('隔离命令失败，见 docker.log')
    return result


def compose(mode, *arguments, input=None, allowed_failure=False):
    files = ['docker-compose.yml', 'compose.minimal.yml', str(FOLDER / 'override.yml')]
    if mode == 'on': files.append(str(FOLDER / 'on.yml'))
    command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env')]
    for file in files: command += ['-f', file]
    return run(command + list(arguments), input=input, allowed_failure=allowed_failure)


def check(label, condition):
    if not condition: raise AssertionError(label)
    CHECKS.append(label)
    print('通过：' + label, flush=True)


def snippet(code, mode='on'):
    prefix = "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); import django; django.setup(); from django.conf import settings; assert settings.DATABASES['default']['NAME']=='example_fixture'\n"
    return compose(mode, 'exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=prefix + code).stdout.strip()


def api(path, *, token=None, method='GET', data=None, expected=200, headers=None):
    response = requests.request(method, BASE + path, json=data,
        headers={**({'Authorization': 'Bearer ' + token} if token else {}), **(headers or {})}, timeout=15)
    check(method + ' ' + path + ' → ' + str(expected), response.status_code == expected)
    return response


def login(username, password):
    return api('auth/login/', method='POST', data={'username': username, 'password': password}).json()['access']


def ready():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if requests.get(BASE + 'health/', timeout=2).status_code == 200: return
        except requests.RequestException:
            pass
        time.sleep(0.2)
    raise RuntimeError('隔离入口未恢复就绪')


def main():
    for port in PORTS:
        with socket.socket() as listener: listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password, member_password = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    env_file = FOLDER / 'fixture.env'
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'example_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
        'DJANGO_DEBUG': 'False', 'BACKEND_PORT': '18440', 'FRONTEND_PORT': '18441',
        'AUTH_LOGIN_CAPTCHA_ENABLED': 'False', 'USE_TLS': 'False'}
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    override = 'services:\n'
    for service in ['backend', 'worker', 'beat']:
        override += f'  {service}:\n    env_file: !override\n      - "{env_file.as_posix()}"\n    image: {PROJECT}-backend\n'
    override += f'  frontend:\n    image: {PROJECT}-frontend\n    ports: !override\n      - "127.0.0.1:18441:80"\n'
    (FOLDER / 'override.yml').write_text(override, encoding='utf-8')
    # 只有示例和参数管理，无 Redis/worker/beat 依赖。
    (FOLDER / 'on.yml').write_text('services:\n  backend:\n    environment:\n      ADMINCORE_MODULES: example,system\n', encoding='utf-8')
    report = {'passed': False, 'project': PROJECT, 'ports': PORTS}
    try:
        compose('off', 'build', 'backend', 'frontend')
        compose('off', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'backend', 'frontend')
        ready()
        check('三服务示例验收无队列依赖', set(compose('off', 'ps', '--status', 'running', '--services').stdout.split()) == {'db', 'backend', 'frontend'})
        token = login('admin', password)
        api('auth/change_password/', token=token, method='POST', data={'old_password': password, 'new_password': member_password, 'new_password2': member_password})
        token = login('admin', member_password)
        capabilities = api('modules/', token=token).json()['data']
        check('所有预设默认关闭示例且仍保留范围声明', not next(row for row in capabilities['modules'] if row['key'] == 'example')['enabled']
              and {'key': 'example', 'title': '示例工单'} in capabilities['scope_resources'])
        api('example/items/', token=token, expected=404)
        compose('on', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend')
        ready()
        capabilities = api('modules/', token=token).json()['data']
        check('显式开启后声明页面权限', next(row for row in capabilities['modules'] if row['key'] == 'example')['page_permissions'] == {'/example': 'example:read'})
        check('菜单只在首次启用初始化', sum(row['path'] == '/example' for row in api('permissions/menus/my_menu/', token=token).json()['data']) == 1)
        snippet(f'''from django.contrib.auth import get_user_model
from apps.permissions.models import Role, Permission, RolePermission, UserRole
User=get_user_model()
member=User.objects.create_user('sample_member',password={member_password!r})
role=Role.objects.create(name='example-owner')
UserRole.objects.create(user=member,role=role)
for permission in Permission.objects.filter(code__startswith='example:'):
    RolePermission.objects.create(role=role,permission=permission)
print('seeded')
''')
        member_token = login('sample_member', member_password)
        payload = {'title': '私有工单标题', 'notes': '<script>原文显示</script>', 'version': 0}
        first = api('example/items/', method='POST', data=payload, token=member_token, expected=201, headers={'Idempotency-Key': 'real-once'})
        row = first.json()['data']; detail = 'example/items/' + row['id'] + '/'
        repeated = api('example/items/', method='POST', data=payload, token=member_token, expected=201, headers={'Idempotency-Key': 'real-once'})
        check('真实 HTTP 创建重放同一记录', first.json() == repeated.json() and repeated.headers['Idempotency-Replayed'] == 'true')
        other = api('example/items/', method='POST', data={'title': '其他用户记录', 'version': 0}, token=token, expected=201).json()['data']
        api('example/items/' + other['id'] + '/', token=member_token, expected=404)
        response = api('example/items/', token=member_token)
        check('本人范围和分页禁止缓存', response.headers['Cache-Control'] == 'private, no-store'
              and [item['id'] for item in response.json()['data']['items']] == [row['id']])
        api(detail, method='PATCH', token=member_token, data={'version': 0, 'title': '不能覆盖'}, expected=409)
        api(detail, method='PATCH', token=member_token, data={'version': 1, 'status': 'done'})
        check('工单审计不存正文', snippet("from apps.logs.models import OperationLog; rows=OperationLog.objects.filter(resource='example'); assert rows.count()==3; assert all('私有工单' not in str(row.after_values) and '原文显示' not in str(row.after_values) for row in rows); print('safe')") == 'safe')
        api('system/config/example.title_limit/', method='PATCH', token=token, data={'value': 20, 'version': 0})
        api('example/items/', method='POST', token=member_token, data={'title': 'x'*21, 'version': 0}, expected=400)
        compose('on', 'exec', '-T', 'backend', 'python', 'manage.py', 'spectacular', '--validate', '--fail-on-warn', '--file', '/tmp/example-schema.yml')
        check('开启示例的 OpenAPI 无警告', True)
        snippet((ROOT / 'scripts/example_concurrency.py').read_text(encoding='utf-8'))
        check('真实 PostgreSQL 九项并发和锁等待复核', True)
        retained = snippet("from apps.example.models import WorkItem; from apps.core.models import SystemConfig; print((WorkItem.objects.count(),SystemConfig.objects.get(key='example.title_limit').value))")
        compose('off', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend')
        ready()
        api(detail, token=member_token, expected=404)
        api('system/config/example.title_limit/', token=token, expected=404)
        check('关闭与迁移不删除业务和参数', retained == snippet("from apps.example.models import WorkItem; from apps.core.models import SystemConfig; print((WorkItem.objects.count(),SystemConfig.objects.get(key='example.title_limit').value))", 'off'))
        compose('on', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend')
        ready()
        restored = api(detail, token=member_token).json()['data']
        check('重新启用恢复业务版本和参数', restored['version'] == 2 and restored['status'] == 'done'
              and api('system/config/example.title_limit/', token=token).json()['data'][0]['value'] == 20)
        # 模块再次开启也不得复活管理员已删除的菜单。
        snippet("from apps.permissions.models import Menu; Menu.objects.filter(path='/example').delete(); print('deleted')")
        compose('on', 'exec', '-T', 'backend', 'python', 'manage.py', 'bootstrap_admincore')
        check('重复初始化保留菜单管理结果', snippet("from apps.permissions.models import Menu; print(Menu.objects.filter(path='/example').count())") == '0')
        report['passed'] = True
    finally:
        report['checks'] = CHECKS
        if report['passed']:
            compose('on', 'down', '-v', '--remove-orphans')
            env_file.unlink()
            report['cleaned'] = ['isolated containers and volumes', str(env_file)]
        else:
            compose('on', 'logs', '--no-color', allowed_failure=True)
        (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(FOLDER), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
