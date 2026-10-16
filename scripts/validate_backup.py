"""隔离 PostgreSQL/Celery/MinIO 的自动备份、并发领取和真实恢复验收。

只清理此脚本创建的项目、数据目录与 PID；失败保留现场与日志。
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

import boto3
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from backup_runner import Runner, validated_set
from validate_storage import ASSETS, RELEASE


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    project = 'admincore-backup-' + secrets.token_hex(4)
    folder = ROOT / '.codex-validation' / project
    folder.mkdir(parents=True)
    port, api_port = free_port(), free_port()
    name, checksum = ASSETS['Linux']
    binary = ROOT / '.codex-validation' / 'storage-runtime' / name
    if not binary.exists():
        binary.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(f'https://github.com/minio/minio/releases/download/{RELEASE}/{name}', binary)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != checksum:
        raise RuntimeError('MinIO运行时摘要不匹配')
    if os.name != 'nt':
        binary.chmod(0o700)
    access, secret = 'fixture-' + secrets.token_hex(8), secrets.token_urlsafe(40)
    password = secrets.token_urlsafe(40)
    endpoint = f'http://127.0.0.1:{port}'
    container_endpoint = 'http://minio:9000'
    variables = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
                 'DB_NAME': 'backup_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
                 'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production',
                 'DJANGO_DEBUG': 'False', 'BACKEND_PORT': str(api_port), 'FRONTEND_PORT': str(free_port()),
                 'ADMINCORE_BACKUP_ENABLED': 'True', 'ADMINCORE_BACKUP_S3_BUCKET': 'isolated-backups',
                 'ADMINCORE_BACKUP_S3_ENDPOINT': container_endpoint, 'ADMINCORE_BACKUP_S3_ACCESS_KEY': access,
                 'ADMINCORE_BACKUP_S3_SECRET_KEY': secret, 'ADMINCORE_BACKUP_S3_ALLOW_HTTP': 'True',
                 'MINIO_ROOT_USER': access, 'MINIO_ROOT_PASSWORD': secret, 'MINIO_BROWSER': 'off'}
    env_file = folder / 'fixture.env'
    env_file.write_text(''.join(f'{key}={value}\n' for key, value in variables.items()), encoding='utf-8')
    override = 'services:\n'
    for service in ('backend', 'worker', 'beat'):
        override += (f'  {service}:\n    image: {project}-backend\n    env_file: !override\n'
                     f'      - {env_file.as_posix()}\n')
    override += f'  frontend:\n    image: {project}-frontend\n'
    override += (f'  minio:\n    image: {project}-backend\n    entrypoint: /minio\n'
                 f'    command: server /data --address :9000\n    env_file:\n      - {env_file.as_posix()}\n'
                 f'    volumes:\n      - "{binary.as_posix()}:/minio:ro"\n      - backupminio:/data\n'
                 f'    ports:\n      - "127.0.0.1:{port}:9000"\nvolumes:\n  backupminio:\n')
    override_file = folder / 'override.yml'
    override_file.write_text(override, encoding='utf-8')
    compose = ['docker', 'compose', '-p', project, '--env-file', str(env_file), '-f', str(ROOT / 'docker-compose.yml'), '-f', str(override_file)]
    checks, report = [], {'passed': False, 'project': project}
    def run(args, *, source=None):
        result = subprocess.run(compose + args, cwd=ROOT, capture_output=True, input=source, timeout=600)
        with (folder / 'docker.log').open('ab') as log:
            log.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('隔离容器操作失败，详见docker.log')
        return result.stdout
    def shell(code):
        return run(['exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c', code]).decode().splitlines()[-1]
    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        print('通过：' + label, flush=True)
    try:
        run(['build', 'backend', 'frontend'])
        run(['up', '-d', '--no-build', 'minio'])
        for _ in range(100):
            try:
                if requests.get(endpoint + '/minio/health/ready', timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(.2)
        else:
            raise RuntimeError('隔离MinIO未就绪')
        client = boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=access, aws_secret_access_key=secret)
        client.create_bucket(Bucket='isolated-backups')
        run(['up', '-d', '--no-build', '--wait', '--wait-timeout', '150', 'db', 'redis', 'backend', 'worker', 'beat', 'frontend'])
        check('隔离服务健康', requests.get(f'http://127.0.0.1:{api_port}/api/v1/health/', timeout=10).status_code == 200)
        shell("from apps.auth_app.models import User; User.objects.filter(username='admin').update(must_change_password=False)")
        token = requests.post(f'http://127.0.0.1:{api_port}/api/v1/auth/login/', json={'username': 'admin', 'password': password}, timeout=10).json()['access']
        headers = {'Authorization': 'Bearer ' + token}
        url = f'http://127.0.0.1:{api_port}/api/v1/tasks/schedules/'
        rows = requests.get(url, headers=headers, timeout=10).json()['data']
        backup = next(row for row in rows if row['key'] == 'backup')
        check('注册备份默认禁用并明确无删除预览', not backup['enabled'] and not backup['requires_preview'] and backup['time_limit_seconds'] == 7200)
        payload = {'revision': backup['revision'], 'enabled': True, **backup['cron'], 'options': {'dry_run': False}}
        check('后台可更新备份计划', requests.patch(url + 'backup/', headers=headers, json=payload, timeout=10).status_code == 200)
        # 两个 worker 并发登记、两个独立宿主并发领取，数据库约束保证唯一。
        code = "from apps.tasks.tasks import request_backup; request_backup.delay(); request_backup.delay(); print('queued')"
        shell(code)
        for _ in range(50):
            pending = int(shell("from apps.tasks.models import BackupRequest; print(BackupRequest.objects.filter(record__status='pending').count())"))
            if pending:
                break
            time.sleep(.2)
        check('真实Celery重复登记仅一个备份请求', pending == 1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: json.loads(run(['exec', '-T', 'backend', 'python', 'manage.py', 'backup_queue', 'claim'])), range(2)))
        claimed = next(row for row in claims if row)
        check('PostgreSQL跨进程并发领取一次', sum(row is not None for row in claims) == 1)
        run(['exec', '-T', 'backend', 'python', 'manage.py', 'backup_queue', 'fail', claimed['record_id'], '--token', claimed['token'], '--code', 'backup_failed'])
        check('失败任务与管理员通知记录', shell("from apps.tasks.models import TaskRecord; from apps.notifications.models import Notification; print(TaskRecord.objects.filter(error='backup_failed',status='failed').count(), Notification.objects.filter(title='自动备份失败').count())") == '1 1')
        shell("from apps.files.models import FileModel; from django.core.files.uploadedfile import SimpleUploadedFile; from apps.auth_app.models import User; FileModel.objects.create(original_name='restore-fixture.txt',file=SimpleUploadedFile('restore-fixture.txt',b'verified-backup-media'),size=21,uploader=User.objects.get(username='admin')); from apps.tasks.tasks import request_backup; print(request_backup())")
        instance = Runner(folder / 'snapshots', compose=compose)
        start = time.monotonic()
        check('宿主执行器完成停写备份及结果回写', instance.once())
        report['backup_seconds'] = round(time.monotonic() - start, 2)
        marker = next((folder / 'snapshots').glob('*.backup.json'))
        data, paths = validated_set(folder / 'snapshots', marker)
        check('数据库媒体清单完整SHA256验证', len(paths) == 3 and data['remote_copy'])
        status = shell("from apps.tasks.models import TaskRecord; print(TaskRecord.objects.filter(related_resource='maintenance:backup',status='success').count())")
        check('任务中心显示备份成功', status == '1')
        for row in data['artifacts']:
            key = f'admincore-backups/{data["timestamp"]}/{row["name"]}'
            body = client.get_object(Bucket='isolated-backups', Key=key)['Body']
            try:
                checksum = hashlib.sha256(body.read()).hexdigest()
            finally:
                body.close()
            check('独立MinIO副本摘要 ' + row['name'], checksum == row['sha256'])
            check('独立副本禁止匿名读取 ' + row['name'], requests.get(endpoint + '/isolated-backups/' + key, timeout=10).status_code == 403)
        stage = 'backup_restore_fixture'
        start = time.monotonic()
        run(['exec', '-T', 'db', 'sh', '-c', 'createdb -U "$POSTGRES_USER" backup_restore_fixture'])
        run(['exec', '-T', 'db', 'sh', '-c', 'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d backup_restore_fixture'], source=paths[0].read_bytes())
        query = run(['exec', '-T', 'db', 'sh', '-c', 'psql -X -U "$POSTGRES_USER" -d backup_restore_fixture -At -c "SELECT count(*) FROM files_filemodel WHERE original_name = \'restore-fixture.txt\'"']).decode().strip()
        check('真实PostgreSQL隔离恢复业务记录', query == '1')
        with tarfile.open(paths[1], 'r:gz') as archive:
            members = archive.getmembers()
            check('媒体归档恢复内容一致', len(members) == 1 and members[0].name.startswith('media/') and archive.extractfile(members[0]).read() == b'verified-backup-media')
        report['restore_seconds'] = round(time.monotonic() - start, 2)
        check('恢复后应用服务继续健康', requests.get(f'http://127.0.0.1:{api_port}/api/v1/health/', timeout=10).status_code == 200)
        shell("from apps.auth_app.models import User; User.objects.filter(username='admin').update(first_name='changed_after_backup')")
        restore_environment = {**os.environ, **variables, 'COMPOSE_PROJECT_NAME': project,
                               'COMPOSE_FILE': os.pathsep.join([str(ROOT / 'docker-compose.yml'), str(override_file)]),
                               'COMPOSE_PATH_SEPARATOR': os.pathsep,
                               'FRONTEND_URL': 'http://127.0.0.1:' + variables['FRONTEND_PORT']}
        start = time.monotonic()
        backup_url = f'http://127.0.0.1:{api_port}/api/v1/tasks/backups/'
        before = requests.get(backup_url, headers=headers, timeout=10).json()['data']
        check('管理接口展示宿主已校验目录', before['state'] == 'idle' and len(before['artifacts']) == 1)
        preflight = requests.post(backup_url + data['timestamp'] + '/preflight/', headers=headers, json={}, timeout=10)
        check('真实API备份恢复预检', preflight.status_code == 200)
        identifier = preflight.json()['data']['preflight_id']
        submitted = requests.post(backup_url + data['timestamp'] + '/restore/', headers=headers,
            json={'preflight_id': identifier, 'confirmation': '恢复备份', 'current_password': password}, timeout=10)
        check('密码二次确认后恢复登记', submitted.status_code == 202)
        request_id = submitted.json()['data']['id']
        restored = subprocess.run([sys.executable, str(ROOT / 'scripts/backup_runner.py'), '--once',
                                   '--backup-dir', str(folder / 'snapshots')], cwd=ROOT, env=restore_environment,
                                  capture_output=True, timeout=300)
        with (folder / 'restore.log').open('wb') as output:
            output.write(restored.stdout + restored.stderr)
        check('恢复队列统一锁和Git Bash/原生Bash完整恢复链路', restored.returncode == 0)
        check('恢复切换后原业务值正确', shell("from apps.auth_app.models import User; print(User.objects.get(username='admin').first_name == '')") == 'True')
        after = requests.get(backup_url, headers=headers, timeout=10).json()['data']
        check('数据库回退后宿主回执仍显示恢复成功', any(row['id'] == request_id and row['status'] == 'succeeded' for row in after['restore_requests']))
        report['complete_restore_seconds'] = round(time.monotonic() - start, 2)
        report['passed'] = True
    finally:
        run(['logs', '--no-color', 'minio'])
        if not report['passed']:
            run(['stop'])
        if report['passed']:
            run(['down', '--volumes', '--remove-orphans'])
            for directory in ('snapshots',):
                target = (folder / directory).resolve()
                if target.parent != folder.resolve():
                    raise RuntimeError('清理路径越界')
                shutil.rmtree(target)
            env_file.unlink()
            override_file.unlink()
            subprocess.run(['docker', 'image', 'rm', project + '-backend', project + '-frontend'], capture_output=True)
            report['cleaned'] = ['isolated_compose_volumes', 'snapshots', 'fixture.env', 'override.yml', 'isolated_backend_frontend_images']
        report['checks'] = checks
        report['ports'] = [port, api_port]
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(folder), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
