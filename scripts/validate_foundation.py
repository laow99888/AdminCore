"""独立 Docker/PostgreSQL 验收；只移除本脚本创建的项目、卷及临时凭据。

用法：backend/venv/Scripts/python.exe scripts/validate_foundation.py
需要 Docker Compose（支持 !override）、本机 18420/18421 空闲以及 requests。
失败保留隔离项目和日志；成功保留报告，关闭容器并移除本次测试卷。
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import base64
import json
import secrets
import socket
import subprocess
import sys
import time
import uuid

import requests

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-foundation-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
BASE = 'http://127.0.0.1:18421/api/v1/'
CHECKS = []


def run(args, *, allowed_failure=False):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    with (FOLDER / 'docker.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError(f'命令失败，详见 {FOLDER / "docker.log"}')
    return result


def compose(mode, *args):
    files = ['docker-compose.yml', 'compose.minimal.yml', str(FOLDER / 'override.yml')]
    if mode == 'standard':
        files.append(str(FOLDER / 'standard.yml'))
    command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env')]
    for file in files:
        command += ['-f', file]
    return run(command + list(args))


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)
    print('通过：' + label, flush=True)


def api(path, method='GET', data=None, expected=200, token=None, headers=None):
    request_headers = {'Authorization': 'Bearer ' + token} if token else {}
    request_headers.update(headers or {})
    response = requests.request(method, BASE + path, json=data,
                                headers=request_headers, timeout=40)
    if expected is not None:
        check(method + ' ' + path + ' → ' + str(expected), response.status_code == expected)
    return response


def concurrent_patch(path, payloads, token):
    with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
        return sorted(pool.map(lambda payload: api(path, 'PATCH', payload, None, token).status_code, payloads))


def login(password):
    return api('auth/login/', 'POST', {'username': 'admin', 'password': password}).json()['access']


def ready():
    # Compose 只判断后端健康；代理 DNS 刷新有短暂的收敛时间。
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if requests.get(BASE + 'health/', timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError('反向代理未在 30 秒内恢复健康')


def main():
    for port in [18420, 18421]:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password = secrets.token_urlsafe(40)
    environment = {
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'foundation', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
        'DJANGO_DEBUG': 'False', 'FRONTEND_PORT': '18421', 'BACKEND_PORT': '18420',
        'ALLOW_PUBLIC_REGISTRATION': 'False', 'USE_TLS': 'False',
        'AUTH_TOTP_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'),
    }
    env_file = FOLDER / 'fixture.env'
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    override = 'services:\n'
    for service in ['backend', 'worker', 'beat']:
        override += f'  {service}:\n    env_file: !override\n      - {env_file.as_posix()}\n    image: {PROJECT}-backend\n'
    override += f'  frontend:\n    image: {PROJECT}-frontend\n    ports: !override\n      - "127.0.0.1:18421:80"\n'
    (FOLDER / 'override.yml').write_text(override, encoding='utf-8')
    (FOLDER / 'standard.yml').write_text('''services:
  redis:
    profiles: !reset []
  backend:
    environment:
      ADMINCORE_PRESET: standard
      ADMINCORE_MODULES: files,tasks,notifications,data_io,approvals,system,organization
    depends_on: !override
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
''', encoding='utf-8')
    try:
        compose('minimal', 'build', 'backend', 'frontend')
        compose('minimal', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'backend', 'frontend')
        services = compose('minimal', 'ps', '--status', 'running', '--services').stdout.split()
        check('精简部署只有数据库、后端、前端', set(services) == {'db', 'backend', 'frontend'})
        for service in services:
            container = compose('minimal', 'ps', '-q', service).stdout.strip()
            configuration = json.loads(run(['docker', 'inspect', container, '--format', '{{json .HostConfig.LogConfig}}']).stdout)
            check('真实容器日志有界轮转 ' + service, configuration == {
                'Type': 'json-file', 'Config': {'max-size': '10m', 'max-file': '3'}})
        api('health/')
        token = login(password)
        check('新初始化账号必须改密', api('auth/me/', token=token).json()['data']['must_change_password'])
        blocked = api('users/', expected=403, token=token).json()
        check('改密前服务端禁止业务访问', blocked['data']['reason'] == 'password_change_required')
        new_password = secrets.token_urlsafe(40)
        api('auth/change_password/', 'POST', {'old_password': password, 'new_password': new_password,
                                            'new_password2': new_password}, token=token)
        api('auth/me/', expected=401, token=token)
        password = new_password
        token = login(password)
        check('改密后解除限制', not api('auth/me/', token=token).json()['data']['must_change_password'])
        devices = api('auth/sessions/', token=token)
        check('精简部署保留本人设备入口且禁止缓存',
              devices.headers['Cache-Control'] == 'private, no-store'
              and len(devices.json()['data']['items']) == 1
              and devices.json()['data']['items'][0]['is_current'])
        recovery = api('auth/recovery/config/')
        check('精简部署匿名找回配置明确关闭且不缓存', recovery.json()['data'] == {'enabled': False}
              and recovery.headers['Cache-Control'] == 'private, no-store')
        api('auth/recovery/request/', 'POST', {'username': 'admin', 'email': 'fixture@example.test'}, 503)
        api('auth/email-verification/request/', 'POST', {'current_password': password}, 503, token)
        captcha = api('auth/login-captcha/', 'POST', {'username': 'admin'})
        check('精简部署默认关闭图形验证码且响应禁止缓存', captcha.json()['data'] == {'required': False}
              and captcha.headers['Cache-Control'] == 'private, no-store')
        encoded = base64.b64encode((ROOT / 'scripts/validate_login_captcha.py').read_bytes()).decode('ascii')
        compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('精简部署无Redis的PostgreSQL跨进程验证码共享、消费与门槛验收', True)
        encoded = base64.b64encode((ROOT / 'scripts/validate_sensitive_fields.py').read_bytes()).decode('ascii')
        compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('精简部署联系方式脱敏、手机号加密转换与撤销竞争验收', True)
        second_login = api('auth/login/', 'POST', {'username': 'admin', 'password': password}).json()
        rotated = api('auth/refresh/', 'POST', {'refresh': second_login['refresh']}).json()['data']
        check('刷新轮换同时返回新 access 与 refresh', bool(rotated['access']) and bool(rotated['refresh'])
              and rotated['refresh'] != second_login['refresh'])
        api('auth/refresh/', 'POST', {'refresh': second_login['refresh']}, 400)
        api('auth/logout/', 'POST', token=rotated['access'])
        api('auth/me/', expected=401, token=rotated['access'])
        api('auth/refresh/', 'POST', {'refresh': rotated['refresh']}, 400)
        check('当前设备退出后另一设备仍有效', api('auth/me/', token=token).status_code == 200)
        api('auth/online-users/', token=token)
        competing = [secrets.token_urlsafe(40), secrets.token_urlsafe(40)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = list(pool.map(lambda candidate: api('auth/change_password/', 'POST', {
                'old_password': password, 'new_password': candidate, 'new_password2': candidate}, None, token).status_code,
                competing))
        check('PostgreSQL 并发改密只有一次成功，旧凭据不能覆盖新密码', sorted(decisions) == [200, 401])
        password = competing[decisions.index(200)]
        token = login(password)
        capabilities = api('modules/', token=token).json()['data']
        check('精简契约关闭全部可选模块', all(not module['enabled'] for module in capabilities['modules']))
        check('每个内置模块声明版本默认状态和互斥元数据', all(module['contract_version'] == 1
            and type(module['default_enabled']) is bool and isinstance(module['conflicts'], list)
            for module in capabilities['modules']))
        proposal = json.loads(compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py',
            'check_modules', '--modules=files').stdout)
        check('真实精简容器只读预检启用影响且不改运行配置', proposal['enable'] == ['files']
            and proposal['disable'] == [] and proposal['requires_restart']
            and proposal['retains_tables_and_data'] and api('files/', expected=404, token=token).status_code == 404)
        invalid = compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
            "from django.core.management import call_command, CommandError\n"
            "try:\n call_command('check_modules',modules='data_io')\n"
            "except CommandError as exc:\n print(str(exc))\n"
            "else:\n raise AssertionError('must reject missing dependencies')")
        check('真实容器明确拒绝缺失文件和任务依赖', 'data_io' in invalid.stdout
            and 'files' in invalid.stdout and 'tasks' in invalid.stdout)
        api('system/config/', expected=404, token=token)
        api('files/', expected=404, token=token)
        check('精简部署可编辑本人资料且头像关闭', not api('auth/profile/', token=token).json()['data']['avatar_enabled'])
        api('auth/profile/', 'PATCH', {'profile_version': 1, 'bio': '精简个人资料'}, token=token)
        api('auth/avatar/', expected=404, token=token)
        compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "from apps.core.models import SystemConfig; SystemConfig.objects.create(key='brand.name',value='迁移保留品牌')")
        compose('standard', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'redis', 'backend', 'frontend')
        ready()
        token = login(password)
        check('精简库重新启用模块保留历史配置', api('brand/').json()['data']['name'] == '迁移保留品牌')
        info = api('system/information/', token=token)
        details = info.json()['data']
        check('诊断显示容器实际 Python、PostgreSQL、Redis 版本', details['python'] == '3.13.15'
              and details['environment'] == 'production'
              and next(item for item in details['services'] if item['name'] == 'database')['version'].startswith('18.6')
              and next(item for item in details['services'] if item['name'] == 'cache')['version'] == '8.10.2')
        check('诊断 HTTP 响应不缓存', info.headers['Cache-Control'] == 'private, no-store')
        check('真实诊断队列与零样本明确区分', details['task_metrics']['status'] == 'ok'
              and details['task_metrics']['broker'] == {'status': 'ok', 'ready': 0}
              and details['task_metrics']['task_records']['duration_seconds']['average'] is None)
        check('存活探针仅返回状态且禁止缓存', api('health/live/').json() == {'status': 'ok'}
              and 'no-store' in api('health/live/').headers['Cache-Control'])
        snapshot = api('system/monitor/', token=token).json()['data']
        check('真实 Linux 容器 CPU、内存和进程采集', snapshot['scope'] == 'container'
              and 0 <= snapshot['cpu']['percent'] <= 100 and snapshot['memory']['used_bytes'] > 0
              and snapshot['processes_supported'] and len(snapshot['processes']) > 0
              and all(set(item) == {'pid', 'kind', 'state', 'cpu_seconds', 'rss_bytes', 'uptime_seconds'} for item in snapshot['processes']))
        api('system/information/', expected=401)
        api('system/monitor/', 'POST', {}, 405, token)
        # 保留 DNS/地址，仅冻结服务，测量探针自身的超时而非容器移除后的 DNS 收敛。
        compose('standard', 'pause', 'redis')
        try:
            started = time.monotonic()
            degraded = api('system/information/', token=token).json()['data']
            check('Redis 无响应诊断仍返回数据库正常及缓存/代理不可用',
                  [item['status'] for item in degraded['services']] == ['ok', 'unavailable', 'unavailable'])
            check('Redis 无响应队列指标为未知且进程仍存活',
                  degraded['task_metrics']['broker'] == {'status': 'unavailable', 'ready': None}
                  and api('health/live/').status_code == 200 and api('health/', expected=503).json() == {'status': 'unavailable'})
            elapsed = time.monotonic() - started
            check(f'本地 Redis 无响应时诊断在 3 秒内退化（实测 {elapsed:.3f} 秒）', elapsed < 3)
        finally:
            compose('standard', 'unpause', 'redis')
            ready()
        # 完整停机仍检查实际降级状态；DNS/网络收敛不算作 socket 探针的响应 SLA。
        compose('standard', 'stop', 'redis')
        try:
            degraded = api('system/information/', token=token).json()['data']
            check('Redis 容器停机诊断仍返回数据库正常及缓存/代理不可用',
                  [item['status'] for item in degraded['services']] == ['ok', 'unavailable', 'unavailable'])
        finally:
            compose('standard', 'start', 'redis')
            ready()
        version = api('auth/profile/', token=token).json()['data']['profile_version']
        statuses = concurrent_patch('auth/profile/', [{'profile_version': version, 'bio': name} for name in ['窗口甲', '窗口乙']], token)
        check('PostgreSQL 本人资料同版本并发仅一次成功', statuses == [200, 409])
        statuses = concurrent_patch('system/config/files.retention_days/', [{'value': value, 'version': 0} for value in [45, 60, 75, 90]], token)
        check('PostgreSQL 并发首次配置仅一次成功', statuses == [200, 409, 409, 409])
        config = api('system/config/files.retention_days/', token=token).json()['data'][0]
        retained = config['value']
        row = api('system/dictionaries/', 'POST', {'code': 'integration', 'name': '并发测试', 'items': [], 'version': 0}, 201, token).json()['data']
        statuses = concurrent_patch('system/dictionaries/' + row['id'] + '/', [{'name': name, 'version': 1} for name in ['甲', '乙']], token)
        check('PostgreSQL 字典编辑冲突不覆盖', statuses == [200, 409])
        # All cache fixtures below belong to this isolated random Compose project.
        api('system/cache/', expected=401)
        catalog = api('system/cache/', token=token).json()['data']
        check('缓存目录使用共享 Redis 且只登记两个命名空间', catalog['backend'] == 'shared'
              and {entry['namespace'] for entry in catalog['namespaces']} == {'configuration', 'dictionaries'})
        warm = (
            "from django.core.cache import cache; from apps.core.models import SystemConfig,DataDictionary; "
            "from apps.core.system_config import config_value; from apps.core.cache_keys import config_cache_key,dictionary_cache_key; "
            "r=SystemConfig.objects.get(key='files.retention_days'); d=DataDictionary.objects.get(code='integration'); "
            "config_value(r.key); cache.set(dictionary_cache_key(d.id,d.version),['cache-fixture'],300); "
            "cache.set('cache-contract-protected-lock','protected',300); "
            "cache.set('throttle_cache_contract','protected',300); "
            "cache.set('cache-contract-protected-session','protected',300)"
        )
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c', warm)
        confirmation = api('system/cache/preview/', 'POST', {'namespace': 'configuration'}, token=token).json()['data']
        api('system/cache/clear/', 'POST', {'namespace': 'configuration', 'token': confirmation['token']}, token=token)
        verify = (
            "from django.core.cache import cache; from apps.core.models import SystemConfig,DataDictionary; "
            "from apps.core.cache_keys import config_cache_key,dictionary_cache_key; "
            "r=SystemConfig.objects.get(key='files.retention_days'); d=DataDictionary.objects.get(code='integration'); "
            "assert cache.get(config_cache_key(r.id,r.version)) is None; "
            "assert cache.get(dictionary_cache_key(d.id,d.version))==['cache-fixture']; "
            "assert all(cache.get(k)=='protected' for k in ['cache-contract-protected-lock','throttle_cache_contract','cache-contract-protected-session']); "
            "from apps.core.system_config import config_value; assert config_value(r.key)==r.value; "
            "assert cache.get(config_cache_key(r.id,r.version))==r.value"
        )
        check('真实 Redis 定向清理、命名空间隔离、锁/限流/会话保护和数据库重建',
              compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c', verify).returncode == 0)
        confirmation = api('system/cache/preview/', 'POST', {'namespace': 'dictionaries'}, token=token).json()['data']
        api('system/cache/clear/', 'POST', {'namespace': 'dictionaries', 'token': confirmation['token']}, token=token)
        check('真实 Redis 字典缓存清理后仍按当前版本返回选项',
              api('system/dictionaries/options/integration/', token=token).json()['data']['version'] == 2)
        departments = [api('organization/departments/', 'POST', {'name': name, 'version': 0}, 201, token).json()['data'] for name in ['甲部门', '乙部门']]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(api, 'organization/departments/' + departments[index]['id'] + '/', 'PATCH',
                                   {'parent': departments[1-index]['id'], 'version': 1}, None, token) for index in [0, 1]]
            statuses = sorted(future.result().status_code for future in futures)
        check('PostgreSQL 并发部门互相挂载不能形成循环', statuses == [200, 400])
        admin_id = api('auth/me/', token=token).json()['data']['id']
        membership = api('organization/memberships/', 'POST', {'user': admin_id, 'department': departments[0]['id'], 'version': 0}, 201, token).json()['data']
        statuses = concurrent_patch('organization/memberships/' + membership['id'] + '/',
                                    [{'department': department['id'], 'version': 1} for department in departments], token)
        check('PostgreSQL 人员归属编辑冲突不覆盖', statuses == [200, 409])
        role = api('permissions/roles/', 'POST', {'name': '并发范围规则'}, 201, token).json()['data']
        grant = api('organization/scopes/', 'POST', {'role': role['id'], 'resource': 'user', 'scope': 'self', 'version': 0}, 201, token).json()['data']
        statuses = concurrent_patch('organization/scopes/' + grant['id'] + '/',
                                    [{'scope': scope, 'departments': [], 'version': 1} for scope in ['all', 'department']], token)
        check('PostgreSQL 数据范围编辑冲突不覆盖', statuses == [200, 409])
        post = api('organization/posts/', 'POST', {'code': 'integration_post', 'name': '验收岗位', 'version': 0}, 201, token).json()['data']
        post_url = 'organization/posts/' + post['id'] + '/'
        statuses = concurrent_patch(post_url, [{'name': name, 'version': 1} for name in ['岗位甲', '岗位乙']], token)
        check('PostgreSQL 岗位同版本并发只有一次成功', statuses == [200, 409])
        assignment_payload = {'user': admin_id, 'post': post['id'], 'version': 0}
        with ThreadPoolExecutor(max_workers=2) as pool:
            assignments = list(pool.map(lambda _: api('organization/user-posts/', 'POST', assignment_payload, None, token), range(2)))
        check('PostgreSQL 重复任职并发返回一次成功和字段错误', sorted(response.status_code for response in assignments) == [201, 400])
        assignment_id = next(response.json()['data']['id'] for response in assignments if response.status_code == 201)
        api(post_url + '?version=2', 'DELETE', expected=400, token=token)
        api(post_url, 'PATCH', {'is_active': False, 'version': 2}, token=token)
        check('停用岗位保留任职且不再出现在可选岗位',
              api('organization/user-posts/', token=token).json()['data']['pagination']['total'] == 1
              and not api('organization/posts/choices/', token=token).json()['data'])
        api('organization/user-posts/', 'POST', assignment_payload, 400, token)
        people = api('approvals/assignees/?search=admin', token=token)
        check('真实 HTTP 目录最小字段且禁止缓存', people.headers['Cache-Control'] == 'private, no-store'
              and set(people.json()['data']['items'][0]) == {'id', 'username', 'display_name', 'department', 'department_name'})
        api('organization/people/', expected=401)
        picker_password = secrets.token_urlsafe(40)
        api('users/', 'POST', {'username': 'picker_member', 'password': picker_password, 'must_change_password': False,
                              'role_ids': [role['id']]}, 201, token)
        api('organization/scopes/' + grant['id'] + '/', 'PATCH', {'scope': 'self', 'departments': [], 'version': 2}, token=token)
        picker_token = api('auth/login/', 'POST', {'username': 'picker_member', 'password': picker_password}).json()['access']
        scoped_people = api('approvals/assignees/', token=picker_token).json()['data']['items']
        check('真实 HTTP user 范围限制人员目录', [item['username'] for item in scoped_people] == ['picker_member'])
        api('approvals/', 'POST', {'title': '范围越权', 'content': '拒绝', 'request_type': 'other', 'assignee_id': admin_id}, 400, picker_token)
        api('organization/posts/', expected=403, token=picker_token)
        api('organization/user-posts/' + assignment_id + '/?version=2', 'DELETE', expected=409, token=token)
        payload = {'title': '并发幂等申请', 'request_type': 'other', 'content': '只执行一次', 'assignee_id': admin_id}
        headers = {'Idempotency-Key': 'postgres-concurrent-create'}
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: api('approvals/', 'POST', payload, None, token, headers), range(4)))
        check('PostgreSQL 同键并发四次只创建一份申请',
              all(response.status_code == 201 for response in responses)
              and len({response.json()['data']['id'] for response in responses}) == 1
              and sum(response.headers.get('Idempotency-Replayed') == 'true' for response in responses) == 3)
        api('approvals/', 'POST', {**payload, 'title': '不同内容'}, 409, token, headers)
        approval_id = responses[0].json()['data']['id']
        decision_headers = {'Idempotency-Key': 'postgres-concurrent-decision'}
        with ThreadPoolExecutor(max_workers=4) as pool:
            decisions = list(pool.map(lambda _: api(f'approvals/{approval_id}/approve/', 'POST', {'comment': ''}, None, token, decision_headers), range(4)))
        check('PostgreSQL 同键审批决策并发全部重放且只执行一次',
              all(response.status_code == 200 for response in decisions)
              and sum(response.headers.get('Idempotency-Replayed') == 'true' for response in decisions) == 3)
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "from concurrent.futures import ThreadPoolExecutor; from django.db import connections; from apps.core.tasks import dispatch_outbox; from apps.core.models import OutboxEvent; from apps.approvals.models import ApprovalRequest; from apps.notifications.models import Notification; "
                "exec('def drain(_):\\n try:\\n  return dispatch_outbox()\\n finally:\\n  connections.close_all()'); "
                "pool=ThreadPoolExecutor(max_workers=4); list(pool.map(drain, range(4))); pool.shutdown(); "
                "assert ApprovalRequest.objects.filter(title='并发幂等申请').count()==1; "
                "assert OutboxEvent.objects.count()==2 and OutboxEvent.objects.filter(status='succeeded').count()==2; "
                "assert Notification.objects.count()==2")
        check('PostgreSQL 四个派发器并发消费两条事件无重复通知', True)
        source = (ROOT / 'scripts/recycle_concurrency.py').read_bytes()
        encoded = base64.b64encode(source).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL 回收站行锁、版本冲突与恢复/清理竞争', True)
        encoded = base64.b64encode((ROOT / 'scripts/profile_concurrency.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL 头像绑定/陈旧删除及删除/上传双向竞争', True)
        encoded = base64.b64encode((ROOT / 'scripts/task_concurrency.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('真实 PostgreSQL 导入逐行提交、并发接续、取消及失联去重', True)
        encoded = base64.b64encode((ROOT / 'scripts/maintenance_concurrency.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL 维护任务会话锁与四次重复领取仅执行一次', True)
        encoded = base64.b64encode((ROOT / 'scripts/announcement_concurrency.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL 公告同版本发布竞争与幂等重放单次审计', True)
        encoded = base64.b64encode((ROOT / 'scripts/session_concurrency.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL 会话刷新轮换、设备撤销隔离和等待写的撤销复核', True)
        encoded = base64.b64encode((ROOT / 'scripts/recovery_concurrency.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL/Redis/本地SMTP 邮箱归属、找回、并发消费及可靠重试', True)
        encoded = base64.b64encode((ROOT / 'scripts/totp_concurrency.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('PostgreSQL/Redis 双因素动态码与恢复码单次消费、会话撤销及失效设置', True)
        encoded = base64.b64encode((ROOT / 'scripts/validate_login_captcha.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('标准部署PostgreSQL/Redis验证码跨进程竞态、第二因素与故障关闭验收', True)
        encoded = base64.b64encode((ROOT / 'scripts/validate_sensitive_fields.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('标准部署联系方式安全导出、手机号加密转换与撤销竞争验收', True)
        announcement = api('notifications/announcements/manage/', 'POST',
                           {'title': '模块切换保留公告', 'content': '隔离验收正文', 'version': 0}, 201, token).json()['data']
        announcement_id = announcement['id']
        api(f'notifications/announcements/manage/{announcement_id}/publish/', 'POST',
            {'version': announcement['version']}, token=token)
        check('真实 HTTP 已发布公告可读',
              api(f'notifications/announcements/{announcement_id}/', token=token).json()['data']['content'] == '隔离验收正文')
        rich_payload = {'title': '富文本隔离验收', 'content_format': 'html', 'version': 0,
                        'content': '<h2>通知</h2><p><strong>安全正文</strong><img src="https://invalid.test/pixel" onerror="alert(1)"></p>'
                                   '<script>alert(2)</script><a href="javascript:alert(3)">危险链接</a>'
                                   '<a href="https://example.test/help">帮助</a>'}
        rich_key = 'foundation-richtext-' + uuid.uuid4().hex
        rich_created = api('notifications/announcements/manage/', 'POST', rich_payload, 201, token,
                           {'Idempotency-Key': rich_key}).json()['data']
        rich_id = rich_created['id']
        check('真实 HTTP 富文本白名单保留排版并移除图片脚本和危险协议',
              rich_created['content_format'] == 'html' and '<strong>安全正文</strong>' in rich_created['content']
              and '<h2>通知</h2>' in rich_created['content'] and 'https://example.test/help' in rich_created['content']
              and all(value not in rich_created['content'].lower() for value in ('<img', '<script', 'onerror', 'javascript:', 'alert('))
              and all(value in rich_created['content'] for value in ('noopener', 'noreferrer', 'nofollow')))
        rich_replay = api('notifications/announcements/manage/', 'POST', rich_payload, 201, token,
                          {'Idempotency-Key': rich_key}).json()['data']
        check('真实 HTTP 富文本幂等重放返回相同安全正文与版本', rich_replay == rich_created)
        api('notifications/announcements/manage/', 'POST', {**rich_payload, 'content': '<p><br></p>'}, 400, token)
        api('notifications/announcements/manage/', 'POST', {**rich_payload, 'content_format': 'markdown'}, 400, token)
        rich_published = api(f'notifications/announcements/manage/{rich_id}/publish/', 'POST',
                             {'version': rich_created['version']}, token=token).json()['data']
        rich_public = api(f'notifications/announcements/{rich_id}/', token=token)
        check('真实 HTTP 发布富文本安全读取且禁止缓存',
              rich_public.headers['Cache-Control'] == 'private, no-store'
              and rich_public.json()['data']['content'] == rich_published['content'] == rich_created['content'])
        plain_markup = '<img src=x onerror=alert(1)>历史纯文本'
        legacy = api('notifications/announcements/manage/', 'POST',
                     {'title': '纯文本兼容', 'content': plain_markup, 'version': 0}, 201, token).json()['data']
        check('真实 HTTP 未指定格式的旧客户端保持纯文本和原始字面标签',
              legacy['content_format'] == 'plain' and legacy['content'] == plain_markup)
        for resource in ('users', 'roles', 'logs', 'files'):
            exported = api(f'data-io/export/?resource={resource}&export_format=csv', token=token)
            check('真实 HTTP 安全导出资源 ' + resource,
                  exported.headers['Content-Type'].startswith('text/csv') and bool(exported.content))
        schedules = api('tasks/schedules/', token=token).json()['data']
        entry = next(item for item in schedules if item['key'] == 'notifications')
        edit = {'revision': entry['revision'], 'enabled': False, **entry['cron'], 'options': {'dry_run': True}}
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: api('tasks/schedules/notifications/', 'PATCH', edit, None, token).status_code, range(2)))
        check('PostgreSQL 维护计划同版本编辑仅一次成功', sorted(statuses) == [200, 409])
        compose('standard', 'up', '-d', '--wait', '--wait-timeout', '150', 'worker')
        source = ('username,email\nhttp_worker_import_1,worker1@example.com\nhttp_worker_import_2,worker2@example.com\n').encode()
        response = requests.post(BASE + 'data-io/import/', headers={'Authorization': 'Bearer ' + token,
            'X-Request-ID': 'http-task-verified'}, data={'resource': 'users'},
            files={'file': ('worker.csv', source, 'text/csv')}, timeout=40)
        check('真实 HTTP 导入可靠入队', response.status_code == 200)
        import_id = response.json()['data']['id']
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            body = api('tasks/' + import_id + '/', token=token).json()
            imported = body.get('data', body)
            if imported['status'] not in ['pending', 'running']: break
            time.sleep(1)
        check('真实 Redis/Celery 导入完成两行且策略可见', imported['status'] == 'success'
              and imported['result']['created'] == 2 and imported['execution']['policy']['hard_timeout'] == 330)
        api('tasks/' + import_id + '/resume/', 'POST', {}, 409, token)
        # 本项目的 SQL 触发器只延迟隔离用户名；强停本项目 worker 模拟进程丢失。
        code = """from django.conf import settings
assert settings.DATABASES['default']['NAME']=='foundation'
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(\"CREATE FUNCTION fixture_import_pause() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.username='http_crash_import_2' THEN PERFORM pg_sleep(50); END IF; RETURN NEW; END $$\")
    cursor.execute(\"CREATE TRIGGER fixture_import_pause BEFORE INSERT ON auth_app_user FOR EACH ROW EXECUTE FUNCTION fixture_import_pause()\")
"""
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c', code)
        response = requests.post(BASE + 'data-io/import/', headers={'Authorization': 'Bearer ' + token},
            data={'resource': 'users'}, files={'file': ('crash.csv', b'username,email\nhttp_crash_import_1,c1@example.com\nhttp_crash_import_2,c2@example.com\n', 'text/csv')}, timeout=40)
        check('真实 worker 中断夹具登记', response.status_code == 200)
        crash_id = response.json()['data']['id']
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            body = api('tasks/' + crash_id + '/', token=token).json()
            crash = body.get('data', body)
            if (crash['result'] or {}).get('created') == 1: break
            time.sleep(0.5)
        check('中断前首行已提交第二行未提交', crash['status'] == 'running' and crash['result'].get('created') == 1)
        compose('standard', 'stop', '-t', '1', 'worker')
        code = """from django.conf import settings
assert settings.DATABASES['default']['NAME']=='foundation'
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from apps.tasks.models import TaskRecord,ImportRowReceipt
from apps.tasks.reliability import recover_lost_imports
from django.contrib.auth import get_user_model
with connection.cursor() as cursor:
    cursor.execute('DROP TRIGGER fixture_import_pause ON auth_app_user')
    cursor.execute('DROP FUNCTION fixture_import_pause()')
assert get_user_model().objects.filter(username='http_crash_import_1').exists()
assert not get_user_model().objects.filter(username='http_crash_import_2').exists()
record=TaskRecord.objects.get(pk='""" + crash_id + """')
assert ImportRowReceipt.objects.filter(batch=record.import_execution.batch).count()==1
TaskRecord.objects.filter(pk=record.pk).update(started_at=timezone.now()-timedelta(hours=1))
recover_lost_imports()
record.refresh_from_db()
assert record.error=='worker_lost_committed_rows_preserved'
"""
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c', code)
        check('真实 worker 强停未提交事务回滚且账本保留', True)
        resumed = api('tasks/' + crash_id + '/resume/', 'POST', {}, 202, token).json()['data']['id']
        compose('standard', 'up', '-d', '--wait', '--wait-timeout', '150', 'worker')
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            body = api('tasks/' + resumed + '/', token=token).json()
            resumed_result = body.get('data', body)
            if resumed_result['status'] not in ['pending', 'running']: break
            time.sleep(0.5)
        check('真实 worker 重启接续只写第二行', resumed_result['status'] == 'success'
              and resumed_result['result']['created'] == 2 and resumed_result['execution']['attempt'] == 2)
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "from apps.notifications.models import Notification; from django.contrib.auth import get_user_model; from django.utils import timezone; from datetime import timedelta; n=Notification.objects.create(recipient=get_user_model().objects.get(username='admin'),title='维护删除隔离夹具',is_read=True); Notification.objects.filter(pk=n.pk).update(read_at=timezone.now()-timedelta(days=200))")
        entry = next(item for item in api('tasks/schedules/', token=token).json()['data'] if item['key'] == 'notifications')
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: api('tasks/schedules/notifications/run/', 'POST',
                {'revision': entry['revision'], 'options': {'dry_run': True}}, None, token,
                {'Idempotency-Key': 'postgres-celery-maintenance', 'X-Request-ID': 'diagnostic-maintenance-http'}), range(2)))
        check('真实维护请求并发同键仅登记一次', all(response.status_code == 202 for response in responses)
              and len({response.json()['data']['id'] for response in responses}) == 1)
        identifier = responses[0].json()['data']['id']
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            body = api('tasks/' + identifier + '/', token=token).json()
            result = body.get('data', body)
            if result['status'] not in ['pending', 'running']:
                break
            time.sleep(1)
        check('真实 Nginx/PostgreSQL/Redis/Celery 可靠事件至预览完成',
              result['status'] == 'success' and result['result']['dry_run'] is True and result['result']['deleted_notifications'] == 0)
        log_text = compose('standard', 'logs', '--no-color', 'backend', 'worker').stdout
        records = []
        for line in log_text.splitlines():
            start = line.find('{')
            if start < 0:
                continue
            try:
                row = json.loads(line[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                records.append(row)
        linked = [row for row in records if row.get('request_id') == 'diagnostic-maintenance-http']
        check('真实 HTTP→outbox→Celery 日志关联 ID 连续',
              any(row.get('event') == 'http.completed' for row in linked)
              and any(row.get('event') == 'outbox.succeeded' and row.get('record_id') == identifier for row in linked)
              and any(row.get('event') == 'task.started' and row.get('task_id') == identifier for row in linked)
              and any(row.get('event') == 'task.finished' and row.get('task_id') == identifier and row.get('task_state') == 'SUCCESS' for row in linked))
        task_metrics = api('system/information/', token=token).json()['data']['task_metrics']
        check('真实任务耗时与关联计数进入只读诊断', task_metrics['task_records']['duration_seconds']['count'] > 0
              and task_metrics['task_records']['duration_seconds']['p95'] is not None
              and task_metrics['correlation']['task_request_linked'] > 0)
        check('暂停定时计划仍允许显式手动预览', not entry['enabled'])
        entry = next(item for item in api('tasks/schedules/', token=token).json()['data'] if item['key'] == 'notifications')
        cleanup = api('tasks/schedules/notifications/run/', 'POST', {'revision': entry['revision'],
            'options': {'dry_run': False}, 'preview_id': identifier, 'confirmation': '执行清理'}, 202, token,
            {'Idempotency-Key': 'postgres-maintenance-cleanup'}).json()['data']['id']
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            body = api('tasks/' + cleanup + '/', token=token).json()
            result = body.get('data', body)
            if result['status'] not in ['pending', 'running']:
                break
            time.sleep(1)
        check('真实 Celery 确认清理仅删除隔离过期通知', result['status'] == 'success' and result['result']['deleted_notifications'] == 1)
        compose('standard', 'stop', 'worker')
        # 在真实 Nginx/PostgreSQL/本地存储链路上验收二进制预览及模块 worker MIME。
        import io
        from PIL import Image
        from pypdf import PdfWriter
        png = io.BytesIO()
        Image.new('RGB', (16, 16), 'blue').save(png, format='PNG')
        version = api('auth/profile/', token=token).json()['data']['profile_version']
        for offset in [0, 1]:
            avatar = requests.post(BASE + 'auth/avatar/', files={'file': ('avatar.png', png.getvalue(), 'image/png')},
                                   data={'profile_version': version + offset}, headers={'Authorization': 'Bearer ' + token}, timeout=20)
            check('真实 HTTP 本人头像上传/替换 ' + str(offset), avatar.status_code == 200 and avatar.json()['data']['has_avatar'])
        avatar = api('auth/avatar/', token=token)
        check('真实 Nginx 私有头像响应和归一化尺寸', avatar.headers['Content-Type'] == 'image/png'
              and avatar.headers['Cache-Control'] == 'private, no-store' and avatar.headers['X-Content-Type-Options'] == 'nosniff'
              and Image.open(io.BytesIO(avatar.content)).size == (256, 256))
        api('auth/avatar/', expected=401)
        api('auth/avatar/', 'DELETE', {'profile_version': version + 1}, 409, token)
        api('auth/avatar/', 'DELETE', {'profile_version': version + 2}, token=token)
        api('auth/avatar/', expected=404, token=token)
        check('头像不进入普通文件回收站', api('files/recycle/', token=token).json()['data']['pagination']['total'] == 0)
        pdf = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.write(pdf)
        for name, content, mime in [('private.png', png.getvalue(), 'image/png'), ('private.pdf', pdf.getvalue(), 'application/pdf')]:
            response = requests.post(BASE + 'files/', files={'file': (name, content, mime)},
                                     headers={'Authorization': 'Bearer ' + token}, timeout=20)
            check('真实 HTTP 上传预览夹具 ' + name, response.status_code == 201)
            preview_path = f"files/{response.json()['id']}/preview/"
            preview = api(preview_path, token=token)
            check('预览内容类型/私有无缓存/安全响应头 ' + name,
                  preview.headers['Content-Type'] == mime and preview.headers['Cache-Control'] == 'private, no-store'
                  and preview.headers['X-Content-Type-Options'] == 'nosniff'
                  and 'sandbox' in preview.headers['Content-Security-Policy'] and len(preview.content) > 0)
            api(preview_path, expected=401)
        origin = BASE.removesuffix('/api/v1/')
        manifest = requests.get(origin + '/.vite/manifest.json', timeout=10).json()
        worker = manifest['node_modules/pdfjs-dist/build/pdf.worker.min.mjs']['file']
        worker_response = requests.get(origin + '/' + worker, timeout=10)
        check('真实 Nginx 模块 worker 使用 JavaScript MIME', worker_response.status_code == 200
              and worker_response.headers['Content-Type'].startswith('application/javascript'))
        check('生产 CSP 允许同源 worker 且禁止 eval', "worker-src 'self'" in worker_response.headers['Content-Security-Policy']
              and "'unsafe-eval'" not in worker_response.headers['Content-Security-Policy'])
        upload = requests.post(BASE + 'files/', files={'file': ('recycle-live.txt', b'live-fixture', 'text/plain')},
                               headers={'Authorization': 'Bearer ' + token}, timeout=20)
        check('真实 HTTP 文件上传', upload.status_code == 201)
        # 上传保留已有非分页响应格式，分页接口使用统一 data 包装。
        uploaded = upload.json()
        file_id = uploaded['id']
        api(f'files/{file_id}/', 'DELETE', expected=204, token=token)
        trashed = api('files/recycle/', token=token).json()['data']['items'][0]
        check('真实 HTTP 回收站保留删除操作者和版本', trashed['deleted_by'] == admin_id and trashed['lifecycle_version'] == 2)
        policy = api('files/recycle_policy/', token=token).json()['data']
        check('真实 HTTP 保留期跟随配置且定时计划已启用', policy['retention_days'] == retained and policy['cleanup_enabled'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: api(f'files/{file_id}/restore/', 'POST', {'lifecycle_version': 2}, None, token), range(2)))
        check('真实 HTTP 同版本恢复仅一次成功', sorted(response.status_code for response in responses) == [200, 409])
        downloaded = api(f'files/{file_id}/download/', token=token)
        check('恢复后鉴权下载字节不变', downloaded.content == b'live-fixture')
        api(f'files/{file_id}/', 'DELETE', expected=204, token=token)
        preview = api('files/recycle_action/', 'POST', {'action': 'purge', 'dry_run': True,
                      'items': [{'id': file_id, 'lifecycle_version': 4}]}, token=token).json()['data']
        check('真实 HTTP 删除预览不删除回收站文件', preview['succeeded'] == 1 and preview['dry_run'])
        lifecycle = next(item for item in api('tasks/schedules/', token=token).json()['data'] if item['key'] == 'lifecycle')
        check('历史清理默认关闭且凌晨四点运行', not lifecycle['enabled'] and lifecycle['cron']['hour'] == '4')
        encoded = base64.b64encode((ROOT / 'scripts/validate_lifecycle.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('真实 PostgreSQL 历史清理、本地对象及导入重试双向竞争验收', True)
        encoded = base64.b64encode((ROOT / 'scripts/validate_change_audit.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('真实 PostgreSQL 审计事务回滚、并发快照连续和只读边界', True)
        encoded = base64.b64encode((ROOT / 'scripts/validate_admin_audit.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('真实 PostgreSQL Django admin 并发前值链与批量审计回滚', True)
        encoded = base64.b64encode((ROOT / 'scripts/validate_message_channels.py').read_bytes()).decode('ascii')
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "import base64; exec(base64.b64decode('" + encoded + "'))")
        check('真实 PostgreSQL 通用通知版本、SMTP 字节及有限重试', True)
        message_template = api('notifications/templates/', 'POST', {'code': 'http-message-fixture', 'name': 'HTTP 通知验收',
            'enabled': True, 'revision': 0, 'subject': 'HTTP ${name}', 'body': 'Body ${name}', 'variables': ['name']}, 201, token).json()['data']
        api('notifications/templates/' + message_template['id'] + '/preview/', 'POST', {'revision': 1, 'values': {'name': 'fixture'}}, token=token)
        actor_id = api('auth/me/', token=token).json()['data']['id']
        message_send = api('notifications/templates/' + message_template['id'] + '/send/', 'POST', {'revision': 1,
            'values': {'name': 'fixture'}, 'recipient_ids': [actor_id], 'channels': ['inapp']}, 202, token,
            {'Idempotency-Key': 'http-message-fixture', 'X-Request-ID': 'diagnostic-notification-http'}).json()['data']
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                'from apps.core.tasks import dispatch_outbox; dispatch_outbox()')
        message_record = api('notifications/deliveries/' + message_send['delivery_ids'][0] + '/', token=token).json()['data']
        check('真实 Nginx HTTP 通知登记及站内派发', message_record['status'] == 'succeeded' and message_record['attempts'] == 1)
        code = """from django.conf import settings
assert settings.DATABASES['default']['NAME']=='foundation'
from apps.notifications.models import MessageDelivery
from apps.core.models import OutboxEvent
row=MessageDelivery.objects.get(pk='""" + message_send['delivery_ids'][0] + """')
assert row.request_id=='diagnostic-notification-http'
assert OutboxEvent.objects.get(event_key='message:'+str(row.pk)).request_id==row.request_id
"""
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c', code)
        check('真实请求→可靠事件→通知投递持久关联一致', True)
        admin_browser = requests.Session()
        admin_login_url = BASE.removesuffix('/api/v1/') + '/admin/login/'
        login_page = admin_browser.get(admin_login_url, timeout=20)
        check('真实 Nginx Django admin 登录页提供 CSRF 校验', login_page.status_code == 200 and 'csrftoken' in admin_browser.cookies)
        login_response = admin_browser.post(admin_login_url, data={'username': 'admin', 'password': password,
            'csrfmiddlewaretoken': admin_browser.cookies.get('csrftoken'), 'next': '/admin/'},
            headers={'Referer': admin_login_url, 'Origin': BASE.removesuffix('/api/v1/')}, allow_redirects=False, timeout=20)
        check('真实 HTTP 隔离管理员登录', login_response.status_code == 302 and 'sessionid' in admin_browser.cookies)
        role_add_url = BASE.removesuffix('/api/v1/') + '/admin/permissions/role/add/'
        role_page = admin_browser.get(role_add_url, timeout=20)
        check('真实 HTTP Django admin 角色表单可访问', role_page.status_code == 200)
        role_payload = {'name': 'http-admin-audit-fixture', 'description': '', 'is_active': 'on',
            '_save': '保存', 'permissions-TOTAL_FORMS': '0', 'permissions-INITIAL_FORMS': '0',
            'permissions-MIN_NUM_FORMS': '0', 'permissions-MAX_NUM_FORMS': '1000',
            'csrfmiddlewaretoken': admin_browser.cookies.get('csrftoken')}
        rejected = admin_browser.post(role_add_url, data=role_payload,
            headers={'Origin': 'https://untrusted.example.test', 'Referer': role_add_url}, allow_redirects=False, timeout=20)
        check('真实 HTTP Django admin 拒绝跨源 CSRF 请求', rejected.status_code == 403)
        response = admin_browser.post(role_add_url, data=role_payload,
            headers={'Referer': role_add_url, 'Origin': BASE.removesuffix('/api/v1/'), 'X-Request-ID': 'foundation-http-admin-create'}, allow_redirects=False, timeout=20)
        check('真实 HTTP 带 CSRF 的后台角色创建', response.status_code == 302)
        logs = api('logs/operation/?request_id=foundation-http-admin-create', token=token).json()['data']['items']
        detail = api('logs/operation/' + logs[0]['id'] + '/', token=token).json()
        check('真实 HTTP Django 后台变更关联到统一前后值', len(logs) == 1 and detail['audit_version'] == 1
              and detail['before_values'] is None and detail['after_values']['name'] == 'http-admin-audit-fixture')
        admin_browser.close()
        audit = api('logs/operation/', token=token, data=None).json()['data']['items'][0]
        detail = api('logs/operation/' + audit['id'] + '/', token=token)
        check('真实 Nginx 审计详情与请求 ID 返回且禁止缓存',
              detail.headers['Cache-Control'] == 'private, no-store' and bool(detail.headers.get('X-Request-ID'))
              and detail.json()['audit_version'] in (0, 1))
        # 仅更改本脚本的随机隔离库：重启播种不能复活已删除菜单或撤销的授权。
        prepare_manifests = (
            "from apps.permissions.models import Menu, RolePermission; "
            "removed=['/files','/tasks/schedules','/system/config','/notifications/templates']; "
            "assert Menu.objects.filter(path__in=removed).count()==4; "
            "Menu.objects.filter(path__in=removed).delete(); "
            "Menu.objects.filter(path='/organization').update(name='本项目组织',order=71,is_visible=False); "
            "RolePermission.objects.order_by('id').first().delete()")
        compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c', prepare_manifests)
        manifest_state = (
            "import json; from django.core.serializers.json import DjangoJSONEncoder; "
            "from apps.permissions.models import Menu,RolePermission; "
            "from apps.core.models import BootstrapState,SystemConfig; "
            "print(json.dumps({'menus':list(Menu.objects.order_by('id').values()),"
            "'grants':list(RolePermission.objects.order_by('id').values()),"
            "'markers':list(BootstrapState.objects.order_by('key').values()),"
            "'parameters':list(SystemConfig.objects.order_by('key').values())},cls=DjangoJSONEncoder))")
        manifest_before = json.loads(compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py',
            'shell', '-c', manifest_state).stdout.strip().splitlines()[-1])
        compose('minimal', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend')
        ready()
        token = login(password)
        api('organization/departments/', expected=404, token=token)
        api('organization/posts/', expected=404, token=token)
        api('organization/people/', expected=404, token=token)
        api('system/dictionaries/', expected=404, token=token)
        api('system/information/', expected=404, token=token)
        api('system/monitor/', expected=404, token=token)
        api('system/cache/', expected=404, token=token)
        api('files/recycle/', expected=404, token=token)
        api('tasks/schedules/', expected=404, token=token)
        api('notifications/announcements/', expected=404, token=token)
        api('notifications/templates/', expected=404, token=token)
        api('notifications/deliveries/', expected=404, token=token)
        api('data-io/resources/', expected=404, token=token)
        api(f'files/{file_id}/restore/', 'POST', {'lifecycle_version': 4}, 404, token)
        compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
                "from apps.core.modules import task_enabled; assert not task_enabled('data_io.run_data_import'); from apps.core.models import DataDictionary; assert DataDictionary.objects.filter(code='integration').exists()")
        compose('standard', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend')
        ready()
        token = login(password)
        manifest_after = json.loads(compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py',
            'shell', '-c', manifest_state).stdout.strip().splitlines()[-1])
        for key, title in [('menus', '菜单删除和定制'), ('grants', '已撤销的角色授权'),
                           ('markers', '历史初始化标记'), ('parameters', '参数覆盖与版本')]:
            check('内置声明迁移后关闭和重启用保留' + title, manifest_after[key] == manifest_before[key])
        check('通知模块关闭/重新启用保留已发布公告',
              api(f'notifications/announcements/{announcement_id}/', token=token).json()['data']['status'] == 'published')
        check('通知模块关闭/重新启用保留富文本格式和消毒结果',
              api(f'notifications/announcements/{rich_id}/', token=token).json()['data'] == rich_published)
        check('关闭并重新启用后参数与字典数据保留', api('system/config/files.retention_days/', token=token).json()['data'][0]['value'] == retained
              and api('system/dictionaries/options/integration/', token=token).json()['data']['version'] == 2)
        check('关闭并重新启用系统诊断恢复只读入口', api('system/information/', token=token).json()['data']['environment'] == 'production')
        check('关闭并重新启用通知保留模板和投递版本', api('notifications/templates/' + message_template['id'] + '/', token=token).json()['data']['revision'] == 1
              and api('notifications/deliveries/' + message_send['delivery_ids'][0] + '/', token=token).json()['data']['version_number'] == 1)
        check('关闭并重新启用缓存管理恢复共享缓存目录', api('system/cache/', token=token).json()['data']['backend'] == 'shared')
        check('关闭并重新启用岗位保留停用状态和历史任职',
              not api(post_url, token=token).json()['data']['is_active']
              and api('organization/user-posts/', token=token).json()['data']['items'][0]['id'] == assignment_id)
        check('文件模块关闭/重新启用保留回收站记录', api('files/recycle/', token=token).json()['data']['items'][0]['id'] == file_id)
        entry = next(item for item in api('tasks/schedules/', token=token).json()['data'] if item['key'] == 'notifications')
        check('任务模块关闭/重新启用保留计划启停和预览参数', not entry['enabled'] and entry['options']['dry_run'])
        check('当前迁移无遗漏', compose('standard', 'exec', '-T', 'backend', 'python', 'manage.py', 'makemigrations', '--check', '--dry-run').returncode == 0)
        command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(env_file), '-f', 'docker-compose.yml',
                   '-f', 'compose.minimal.yml', '-f', str(FOLDER / 'override.yml'), '-f', str(FOLDER / 'standard.yml')]
        for key, value, label in [('ADMINCORE_PRESET', 'demo', '生产配置拒绝演示预设'), ('ADMINCORE_MODULES', 'approvals', '缺失模块依赖立即拒绝启动'),
                                  ('NOTIFICATION_EMAIL_ENABLED', 'True', '通用邮件开启但缺少 SMTP 配置立即拒绝启动')]:
            result = run(command + ['exec', '-T', '-e', key + '=' + value, 'backend', 'python', '-c',
                                    'from django.conf import settings; print(settings.ADMINCORE_MODULES)'], allowed_failure=True)
            check(label, result.returncode != 0 and 'ImproperlyConfigured' in result.stderr)
        # 精简 Compose 的 profiles 可能把已停止的 worker 视为 orphan。
        # 移除仅限本次随机 PROJECT，不能留下占用媒体/日志卷的测试容器。
        compose('standard', '--profile', '*', 'down', '--volumes', '--remove-orphans')
        check('本次隔离容器全部清理', not run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + PROJECT]).stdout.strip())
        check('本次隔离测试卷全部清理', not run(['docker', 'volume', 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + PROJECT]).stdout.strip())
        report = {'project': PROJECT, 'checks': CHECKS, 'passed': True, 'ports': [18420, 18421], 'postgres': '18.6', 'finished_at': time.strftime('%Y-%m-%d %H:%M:%S')}
        (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        env_file.unlink()
        print('独立验收完成，容器和测试卷已清理；报告：' + str(FOLDER / 'report.json'))
    except Exception as exc:
        (FOLDER / 'report.json').write_text(json.dumps({'project': PROJECT, 'checks': CHECKS, 'passed': False, 'error': str(exc)}, ensure_ascii=False, indent=2), encoding='utf-8')
        print('失败证据与隔离项目保留：' + str(FOLDER), file=sys.stderr)
        raise


if __name__ == '__main__':
    main()
