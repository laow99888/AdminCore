"""隔离 PostgreSQL/Gunicorn 原生 ASGI/Nginx 的实际 SSE 验收，无正式凭据/数据。

需要 Docker Compose 和 requests。成功关闭本项目/卷及清理临时凭据，失败保留证据。
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import json
import secrets
import socket
import subprocess
import time
import uuid

import requests

from realtime_capacity import measure

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-realtime-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
PORTS = [18430, 18431]
BASE = 'http://127.0.0.1:18431/api/v1/'
CHECKS = []
STREAMS = []


def run(arguments, *, input=None, allowed_failure=False):
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, input=input,
                            encoding='utf-8', errors='replace', timeout=360)
    with (FOLDER / 'docker.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('隔离命令失败，见 docker.log')
    return result


def compose(mode, *arguments, input=None, allowed_failure=False):
    files = ['docker-compose.yml', 'compose.minimal.yml', 'compose.realtime.yml', str(FOLDER / 'override.yml')]
    if mode == 'channels': files.append(str(FOLDER / 'channels.yml'))
    if mode == 'off': files.append(str(FOLDER / 'off.yml'))
    if mode == 'protocol': files.append(str(FOLDER / 'protocol.yml'))
    command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env')]
    for file in files: command += ['-f', file]
    return run(command + list(arguments), input=input, allowed_failure=allowed_failure)


def check(label, condition):
    if not condition: raise AssertionError(label)
    CHECKS.append(label)
    print('通过：' + label, flush=True)


def snippet(code, mode='channels'):
    prefix = "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); import django; django.setup(); from django.conf import settings; assert settings.DATABASES['default']['NAME']=='realtime_fixture'\n"
    return compose(mode, 'exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=prefix + code).stdout.strip()


def api(path, *, token=None, method='GET', data=None, expected=200):
    response = requests.request(method, BASE + path, json=data,
        headers={'Authorization': 'Bearer ' + token} if token else {}, timeout=15)
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
    raise RuntimeError('隔离 Nginx 入口未恢复就绪')


def stream(token, *, expected=200, headers=None, suffix=''):
    response = requests.get(BASE + 'realtime/events/' + suffix,
        headers={'Authorization': 'Bearer ' + token, **(headers or {})}, stream=True, timeout=(5, 10))
    check('真实 SSE HTTP 状态 ' + str(expected) + '（实际 ' + str(response.status_code) + '）', response.status_code == expected)
    language = 'en' if (headers or {}).get('Accept-Language') == 'en-US' else 'zh-hans'
    check('独立 ASGI 语言协商及缓存区分 ' + language, response.headers.get('Content-Language') == language
        and 'Accept-Language' in response.headers.get('Vary', ''))
    check('独立 ASGI 的成功和拒绝响应透传标准版本通知', response.headers.get('X-API-Version') == 'v1'
        and response.headers.get('Deprecation') == '@1577836800'
        and response.headers.get('Sunset') == 'Wed, 01 Apr 2020 00:00:00 GMT'
        and response.headers.get('Link') == '</api/versions/>; rel="deprecation"')
    STREAMS.append(response)
    return response


def frame(response):
    event, data = '', []
    # 保留同一读取生成器；销毁 urllib3 的 chunked 生成器会关闭连接。
    if not hasattr(response, '_realtime_lines'):
        response._realtime_lines = response.iter_lines(chunk_size=1, decode_unicode=True)
    for line in response._realtime_lines:
        if line.startswith('event:'): event = line[6:].strip()
        if line.startswith('data:'): data.append(line[5:].strip())
        if not line and data: return event, json.loads('\n'.join(data))
    raise AssertionError('SSE 在返回帧之前结束')


def wait_leases(count, mode='channels'):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        value = snippet("from apps.core.models import RealtimeLease; print(RealtimeLease.objects.count())", mode)
        if value == str(count): return True
        time.sleep(0.2)
    return False


def close_streams():
    for response in STREAMS: response.close()
    STREAMS.clear()


def protocol_regression():
    source = (ROOT / 'scripts/sse_protocol_fixture.py').read_text(encoding='utf-8')
    command = "from pathlib import Path; import os; Path('/tmp/sse_protocol_fixture.py').write_text(" + repr(source) + ",encoding='utf-8'); os.execvp('gunicorn', ['gunicorn','sse_protocol_fixture:application','--chdir','/tmp','--worker-class','asgi','--workers','1','--bind','0.0.0.0:8000'])"
    (FOLDER / 'protocol.yml').write_text('services:\n  realtime:\n    entrypoint: ["python"]\n    command: '
                                       + json.dumps(['-c', command]) + '\n', encoding='utf-8')
    try:
        compose('protocol', 'up', '-d', '--wait', '--wait-timeout', '60', '--no-deps', 'realtime')
        deadline = time.monotonic() + 15
        while True:
            response = requests.get(BASE + 'realtime/events/', timeout=(2, 2))
            if response.content == b'isolated-sse-protocol': break
            if time.monotonic() >= deadline: raise AssertionError('协议夹具未就绪')
            time.sleep(.2)
        with requests.Session() as client:
            # 同一客户端连接固定 Nginx worker，稳定命中其上游连接缓存。
            for _ in range(10):
                with client.get(BASE + 'realtime/events/', timeout=(2, 2)) as response:
                    check('真实 Nginx 连续短流不复用仍在异步收尾的上游连接',
                          response.status_code == 200 and response.content == b'isolated-sse-protocol')
    finally:
        compose('minimal', 'up', '-d', '--wait', '--wait-timeout', '60', '--no-deps', 'realtime')


def capacity(stages=((24, 360),), destination=None, *, arrival_seconds=None):
    destination = destination or FOLDER
    destination.mkdir(parents=True, exist_ok=True)
    identifier = compose('channels', 'ps', '-q', 'realtime').stdout.strip()

    def observe():
        code = """import json
from pathlib import Path
root=Path('/sys/fs/cgroup')
def counters(name):
    return {key:int(value) for key,value in (line.split() for line in (root/name).read_text().splitlines())}
print(json.dumps({'memory_current':int((root/'memory.current').read_text()),
 'memory_peak':int((root/'memory.peak').read_text()), 'memory_max':int((root/'memory.max').read_text()),
 'cpu_max':(root/'cpu.max').read_text().strip(), 'memory_events':counters('memory.events'),
 'cpu':counters('cpu.stat')}))"""
        result = json.loads(run(['docker', 'exec', identifier, 'python', '-c', code]).stdout)
        result.update(json.loads(run(['docker', 'inspect', '--format',
            '{"running":{{.State.Running}},"oom_killed":{{.State.OOMKilled}},"restart_count":{{.RestartCount}},"command":{{json .Config.Cmd}}}',
            identifier]).stdout))
        assert result['memory_max'] == 512 * 1024 * 1024 and result['cpu_max'].split() == ['100000', '100000']
        assert result['command'][result['command'].index('--workers') + 1] == '1'
        result.update(json.loads(snippet("""import json
from django.db import connection
from django.utils import timezone
from apps.core.models import RealtimeLease
with connection.cursor() as cursor:
    cursor.execute("SELECT coalesce(state,'unknown'),count(*) FROM pg_stat_activity WHERE datname=current_database() GROUP BY state")
    connections=dict(cursor.fetchall())
print(json.dumps({'total_leases':RealtimeLease.objects.count(),
 'active_leases':RealtimeLease.objects.filter(expires_at__gt=timezone.now()).count(), 'db_connections':connections}))""")))
        return result

    results = []
    for count, seconds in stages:
        prefix = 'capacity-' + secrets.token_hex(4)
        # 仅在受保护的隔离库中通过原生签发服务登记设备；不绕过实际 SSE/refresh 鉴权。
        snippet(f'''import json, os, secrets
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from apps.auth_app.sessions import issue_session
from apps.permissions.models import Role, Permission, RolePermission, UserRole
from apps.core.models import DataScopeGrant
from apps.notifications.models import Notification
from apps.tasks.models import TaskRecord
from apps.approvals.models import ApprovalRequest
role=Role.objects.create(name={prefix!r})
RolePermission.objects.create(role=role,permission=Permission.objects.get(code='task:read'))
DataScopeGrant.objects.create(role=role,resource='task',scope='self')
password=make_password(secrets.token_urlsafe(40))
pairs=[]
for index in range({count + int(count == 100)}):
    user=get_user_model().objects.create(username={prefix!r}+'-'+str(index),password=password,must_change_password=False)
    UserRole.objects.create(user=user,role=role)
    Notification.objects.create(recipient=user,title='PRIVATE_CAPACITY_NOTIFICATION')
    TaskRecord.objects.create(creator=user,name='PRIVATE_CAPACITY_TASK',status='running',progress=37)
    ApprovalRequest.objects.create(applicant=user,assignee=user,title='PRIVATE_CAPACITY_APPROVAL')
    token=issue_session(user)
    pairs.append({{'access':str(token.access_token),'refresh':str(token)}})
with os.fdopen(os.open('/tmp/realtime-capacity-access.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as output:
    json.dump(pairs,output)
print('capacity fixtures ready')
''')
        private_file = FOLDER / 'capacity-access.json'
        try:
            compose('channels', 'cp', 'backend:/tmp/realtime-capacity-access.json', str(private_file))
            actors = json.loads(private_file.read_text(encoding='utf-8'))
        finally:
            private_file.unlink(missing_ok=True)
            compose('channels', 'exec', '-T', 'backend', 'python', '-c',
                    "from pathlib import Path; Path('/tmp/realtime-capacity-access.json').unlink(missing_ok=True)")
        result = measure(BASE, actors[:count], observe, destination / f'capacity-{count}-report.json',
                         seconds=seconds, overflow=actors[-1] if count == 100 else None,
                         arrival_seconds=(.1 if count == 100 else 0) if arrival_seconds is None else arrival_seconds)
        results.append(result)
        check(f'{count}条真实连接持续{seconds}秒、重连/轮换/资源及租约回收', result['passed'])
    return results


def main(*, include_capacity_edge=False, include_capacity_burst=False, burst_only=False):
    for port in PORTS:
        with socket.socket() as listener: listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password, member_password = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    env_file = FOLDER / 'fixture.env'
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'realtime_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
        'DJANGO_DEBUG': 'False', 'BACKEND_PORT': '18430', 'FRONTEND_PORT': '18431',
        'ADMINCORE_MODULES': 'realtime', 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False', 'USE_TLS': 'False',
        'ADMINCORE_API_LIFECYCLE': json.dumps({'v1': {'deprecated_at': '2020-01-01T00:00:00Z',
            'sunset_at': '2020-04-01T00:00:00Z', 'migration_url': '/api/versions/'}}, separators=(',', ':'))}
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    override = 'services:\n'
    for service in ['backend', 'worker', 'beat', 'realtime']:
        override += f'  {service}:\n    env_file: !override\n      - "{env_file.as_posix()}"\n    image: {PROJECT}-backend\n'
        if service == 'realtime': override += '    mem_limit: 512m\n    cpus: 1.0\n'
    override += f'  frontend:\n    image: {PROJECT}-frontend\n    ports: !override\n      - "127.0.0.1:18431:80"\n'
    (FOLDER / 'override.yml').write_text(override, encoding='utf-8')
    (FOLDER / 'channels.yml').write_text('''services:
  redis:
    profiles: !reset []
  backend:
    environment:
      ADMINCORE_MODULES: notifications,tasks,approvals,realtime
    depends_on: !override
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
  realtime:
    environment:
      ADMINCORE_MODULES: notifications,tasks,approvals,realtime
''', encoding='utf-8')
    (FOLDER / 'off.yml').write_text('''services:
  backend:
    environment:
      ADMINCORE_MODULES: ""
  realtime:
    environment:
      ADMINCORE_MODULES: ""
  frontend:
    environment:
      REALTIME_UPSTREAM: backend:8000
''', encoding='utf-8')
    report = {'passed': False, 'project': PROJECT, 'ports': PORTS}
    try:
        compose('minimal', 'build', 'backend', 'frontend')
        if burst_only:
            compose('channels', 'up', '-d', '--wait', '--wait-timeout', '150',
                    'db', 'redis', 'backend', 'frontend', 'realtime')
            ready()
            report['scope'] = '仅百连接瞬时突发，不代替功能与六分钟基线'
            report['capacity'] = capacity(stages=((100, 35),), arrival_seconds=0)
            report['passed'] = True
            return
        compose('minimal', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'backend', 'frontend', 'realtime')
        ready()
        protocol_regression()
        services = compose('minimal', 'ps', '--status', 'running', '--services').stdout.split()
        check('精简 SSE 四服务无需 Redis/worker/beat', set(services) == {'db', 'backend', 'frontend', 'realtime'})
        for language, message in [('en-US', 'The sign-in credentials have expired.'), ('zh-CN', '登录凭据已失效')]:
            denied = stream('', expected=401, headers={'Accept-Language': language})
            check('真实 Nginx/SSE 拒绝消息本地化 ' + language, denied.json()['message'] == message)
            denied.close()
        token = login('admin', password)
        api('auth/change_password/', token=token, method='POST', data={'old_password': password, 'new_password': member_password, 'new_password2': member_password})
        token = login('admin', member_password)
        response = stream(token)
        check('Nginx 实际即时流式返回与安全头', response.headers['Content-Type'].startswith('text/event-stream')
            and response.headers['Cache-Control'] == 'private, no-store' and response.headers['X-Content-Type-Options'] == 'nosniff')
        event, value = frame(response)
        check('仅 realtime 模块不读取/广播业务频道', event == 'snapshot' and value['topics'] == {})
        response.close()
        check('真实断线立即释放短期租约', wait_leases(0, 'minimal'))
        compose('channels', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'redis', 'backend', 'frontend', 'realtime')
        ready()
        seed = f'''from django.contrib.auth import get_user_model
from apps.permissions.models import Role, Permission, RolePermission, UserRole
from apps.core.models import DataScopeGrant
from apps.notifications.models import Notification
from apps.tasks.models import TaskRecord
from apps.approvals.models import ApprovalRequest
User=get_user_model()
member=User.objects.create_user('stream_member','member@example.test',{member_password!r},must_change_password=False)
other=User.objects.create_user('stream_other','other@example.test',{member_password!r},must_change_password=False)
role=Role.objects.create(name='SSE self')
UserRole.objects.create(user=member,role=role)
RolePermission.objects.create(role=role,permission=Permission.objects.get(code='task:read'))
DataScopeGrant.objects.create(role=role,resource='task',scope='self')
Notification.objects.create(recipient=member,title='PRIVATE_MEMBER_BODY')
Notification.objects.create(recipient=other,title='PRIVATE_OTHER_BODY')
TaskRecord.objects.create(creator=member,name='PRIVATE_TASK_NAME',status='running',progress=37,error='PRIVATE_TASK_ERROR')
TaskRecord.objects.create(creator=other,name='PRIVATE_OTHER_TASK',status='running')
ApprovalRequest.objects.create(applicant=other,assignee=member,title='PRIVATE_APPROVAL_TITLE')
ApprovalRequest.objects.create(applicant=other,assignee=other,title='PRIVATE_OTHER_APPROVAL')
print('seeded')
'''
        snippet(seed)
        member_token = login('stream_member', member_password)
        response = stream(member_token, headers={'Origin': 'http://127.0.0.1:18431', 'X-Request-ID': 'realtime-fixture'})
        first, value = frame(response)
        topics = value['topics']
        check('真实 PostgreSQL 按收件人/参与人/任务数据范围返回', topics['notifications']['total'] == topics['notifications']['unread_count'] == 1
            and topics['approvals']['total'] == topics['approvals']['todo_count'] == 1
            and topics['tasks']['total'] == 1 and topics['tasks']['active'][0]['progress'] == 37)
        check('真实流无正文/结果/凭据并串联安全请求 ID', value['request_id'] == 'realtime-fixture' and 'PRIVATE_' not in json.dumps(value)
            and member_token not in json.dumps(value))
        started = time.monotonic()
        api('health/')
        check('保持 SSE 时普通同步 API 不被连接占用', time.monotonic() - started < 3)
        stream(member_token, expected=429).close()
        stream(member_token, expected=400, suffix='?token=forbidden').close()
        stream(member_token, expected=400, headers={'Origin': 'https://forged.example'}).close()
        snippet("from apps.permissions.models import Role; Role.objects.filter(name='SSE self').update(is_active=False)")
        event, updated = frame(response)
        check('保持连接的下一帧复核角色撤权', event == 'snapshot' and 'tasks' not in updated['topics'])
        api('auth/logout/', token=member_token, method='POST', data={})
        event, updated = frame(response)
        check('保持连接的下一帧拒绝设备撤销', event == 'access_revoked' and set(updated) == {'request_id'})
        response.close()
        check('撤销连接释放租约', wait_leases(0))
        tokens = [login('stream_other', member_password) for _ in range(4)]
        for credential in tokens[:3]: frame(stream(credential))
        stream(tokens[3], expected=429).close()
        check('真实 SQL 跨设备同用户三连接上限', snippet("from apps.core.models import RealtimeLease; print(RealtimeLease.objects.count())") == '3')
        close_streams()
        check('关闭各设备连接后额度恢复', wait_leases(0))
        concurrent_token = login('stream_other', member_password)
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: requests.get(BASE + 'realtime/events/', headers={'Authorization': 'Bearer ' + concurrent_token}, stream=True, timeout=(5, 10)), range(8)))
        STREAMS.extend(responses)
        check('真实 PostgreSQL 八并发同设备唯一领取且无死锁', sorted(row.status_code for row in responses) == [200] + [429]*7)
        close_streams()
        check('并发断线恢复额度', wait_leases(0))
        # 正式 SQL global cap 用隔离租约填充；不冒充百连接容量压测。
        snippet('''from datetime import timedelta
from django.utils import timezone
from apps.auth_app.models import AuthSession
from apps.core.models import RealtimeLease
from django.contrib.auth import get_user_model
u=get_user_model().objects.get(username='stream_other')
for index in range(100):
    session=AuthSession.objects.create(user=u,session_version=u.session_version,password_hash='fixture',refresh_jti='fixture-'+str(index),created_at=timezone.now(),expires_at=timezone.now()+timedelta(hours=1),last_seen_at=timezone.now())
    RealtimeLease.objects.create(session=session,expires_at=timezone.now()+timedelta(minutes=1))
print('filled')
''')
        stream(token, expected=429).close()
        check('全局一百有效租约上限独立于请求用户', snippet("from apps.core.models import RealtimeLease; print(RealtimeLease.objects.count())") == '100')
        snippet("from apps.core.models import RealtimeLease; from django.utils import timezone; from datetime import timedelta; RealtimeLease.objects.update(expires_at=timezone.now()-timedelta(seconds=1))")
        recovered = stream(token)
        frame(recovered); recovered.close()
        check('崩溃/过期租约不阻塞新用户连接', True)
        retained = snippet("from apps.notifications.models import Notification; from apps.tasks.models import TaskRecord; from apps.approvals.models import ApprovalRequest; print((Notification.objects.count(),TaskRecord.objects.count(),ApprovalRequest.objects.count()))")
        compose('off', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend')
        ready()
        stream(token, expected=404).close()
        check('关闭模块保留既有业务数据', retained == snippet("from apps.notifications.models import Notification; from apps.tasks.models import TaskRecord; from apps.approvals.models import ApprovalRequest; print((Notification.objects.count(),TaskRecord.objects.count(),ApprovalRequest.objects.count()))", 'off'))
        compose('channels', 'up', '-d', '--wait', '--wait-timeout', '150', 'backend', 'frontend', 'realtime')
        ready()
        event, value = frame(stream(token))
        check('模块关闭期间升级及重新启用恢复', event == 'snapshot' and 'tasks' in value['topics'])
        close_streams()
        # 前面人为填充的百条过期租约属于基线，容量阶段另用真实 HTTP 长连接。
        stages = ((24, 360), (100, 35)) if include_capacity_edge else ((24, 360),)
        report['capacity'] = capacity(stages=stages)
        if include_capacity_burst:
            report['burst'] = capacity(stages=((100, 35),), destination=FOLDER / 'burst', arrival_seconds=0)
        report['passed'] = True
    finally:
        close_streams()
        report['checks'] = CHECKS
        try:
            if report['passed']:
                compose('channels', 'down', '-v', '--remove-orphans')
                run(['docker', 'image', 'rm', PROJECT + '-backend', PROJECT + '-frontend'])
                env_file.unlink()
                report['cleaned'] = ['isolated containers, volumes and image tags', str(env_file)]
            else:
                compose('channels', 'logs', '--no-color', allowed_failure=True)
                compose('channels', 'stop', allowed_failure=True)
        except Exception:
            report['passed'] = False
            report['cleanup_failed'] = True
            compose('channels', 'stop', allowed_failure=True)
            raise
        finally:
            (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'evidence': str(FOLDER), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-capacity-edge', action='store_true',
                        help='另执行每0.1秒到达一条的100条真实连接基线；不等同百条瞬时突发')
    parser.add_argument('--burst-only', action='store_true',
                        help='只复现百条瞬时突发，保留真实代理/鉴权/数据库和原资源限额')
    parser.add_argument('--include-capacity-burst', action='store_true',
                        help='完整验收后另执行百条同步突发连接，不代替六分钟及较缓到达基线')
    arguments = parser.parse_args()
    if arguments.burst_only and (arguments.include_capacity_edge or arguments.include_capacity_burst):
        parser.error('--burst-only 不能与完整验收的追加阶段同时使用')
    main(include_capacity_edge=arguments.include_capacity_edge,
         include_capacity_burst=arguments.include_capacity_burst, burst_only=arguments.burst_only)
