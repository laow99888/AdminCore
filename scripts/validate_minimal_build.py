"""真实裁剪镜像/空库/完整升级/再裁剪验收；只清理本次隔离项目。"""
from pathlib import Path
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
import uuid

import requests

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'admincore-minimal-build-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
PORTS = [18480, 18481]
BASE = 'http://127.0.0.1:18481/api/v1/'
CHECKS = []


def run(arguments, *, input=None, allowed_failure=False):
    with (FOLDER / 'contract.log').open('a', encoding='utf-8') as log:
        offset = log.tell()
        result = subprocess.run(arguments, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True,
            input=input, encoding='utf-8', errors='replace', timeout=600)
    with (FOLDER / 'contract.log').open(encoding='utf-8') as log:
        log.seek(offset)
        result.stdout, result.stderr = log.read(), ''
    if result.returncode and not allowed_failure:
        raise RuntimeError('精简构建隔离验收失败，见 contract.log')
    return result


def compose(mode, *arguments, **kwargs):
    command = ['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env')]
    files = ['docker-compose.yml', 'compose.minimal.yml']
    if mode == 'minimal': files += ['compose.build-minimal.yml']
    files += [str(FOLDER / 'override.yml')]
    if mode == 'full': files += [str(FOLDER / 'full.yml')]
    for file in files: command += ['-f', file]
    return run(command + list(arguments), **kwargs)


def check(label, condition=True):
    if not condition: raise AssertionError(label)
    CHECKS.append(label)
    print('通过：' + label, flush=True)


def snippet(code, mode='minimal'):
    prefix = "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); import django; django.setup(); from django.conf import settings; assert settings.DATABASES['default']['NAME']=='minimal_build_fixture'\n"
    return compose(mode, 'exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=prefix + code).stdout.strip()


def api(path, token=None, method='GET', data=None, expected=200):
    response = requests.request(method, BASE + path, headers={'Authorization': 'Bearer ' + token} if token else {}, json=data, timeout=30)
    check(method + ' ' + path + ' → ' + str(expected), response.status_code == expected)
    return response


def ready():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if requests.get(BASE + 'health/', timeout=3).status_code == 200: return
        except requests.RequestException: pass
        time.sleep(1)
    raise RuntimeError('隔离入口健康检查未恢复')


def main():
    for port in PORTS:
        with socket.socket() as listener: listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True)
    password, changed = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    env_file = FOLDER / 'fixture.env'
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'minimal_build_fixture', 'DB_USER': 'postgres', 'ADMINCORE_ADMIN_PASSWORD': password,
        'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend', 'DJANGO_ENV': 'production', 'DJANGO_DEBUG': 'False',
        'BACKEND_PORT': '18480', 'FRONTEND_PORT': '18481', 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False', 'USE_TLS': 'False'}
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    (FOLDER / 'override.yml').write_text(f"""services:
  backend:
    image: {PROJECT}-backend
    env_file: !override
      - "{env_file.as_posix()}"
  frontend:
    image: {PROJECT}-frontend
    ports: !override
      - "127.0.0.1:18481:80"
""", encoding='utf-8')
    (FOLDER / 'full.yml').write_text("""services:
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
""", encoding='utf-8')
    node_bin = ROOT / '.codex-validation/toolchains/node-v24.21.0-win-x64/node.exe'
    node = str(node_bin) if os.name == 'nt' and node_bin.exists() else shutil.which('node')
    if not node: raise RuntimeError('验收需要Node.js和Playwright Chromium')
    report = {'passed': False, 'project': PROJECT, 'ports': PORTS}
    retained = "from django.contrib.auth import get_user_model; from apps.files.models import FileModel; from apps.core.models import SystemConfig; from django.db.migrations.recorder import MigrationRecorder; import hashlib,json; u=get_user_model().objects.get(username='minimal_retained'); f=FileModel.objects.get(original_name='retained.txt'); print(hashlib.sha256(json.dumps([str(u.pk),u.email,u.password,str(f.pk),f.lifecycle_version,f.file.read().decode(),SystemConfig.objects.get(key='brand.name').value,sorted(MigrationRecorder.Migration.objects.values_list('app','name'))],sort_keys=True).encode()).hexdigest())"
    packages = "['pandas','numpy','openpyxl','pypdf','boto3','botocore','storages','nh3']"
    development_packages = "['pytest','black','flake8','django_extensions']"
    def browser(mode):
        run([node, str(ROOT / 'scripts/minimal_build_browser.mjs'), str(ROOT / 'frontend'), str(FOLDER), mode])
    try:
        compose('minimal', 'build', 'backend', 'frontend')
        compose('minimal', 'up', '-d', '--wait', '--wait-timeout', '150', 'db', 'backend', 'frontend')
        ready()
        check('精简镜像只启动数据库/后端/前端', set(compose('minimal', 'ps', '--status', 'running', '--services').stdout.split()) == {'db','backend','frontend'})
        check('被裁剪重依赖及开发工具实际不可导入', snippet('import importlib.util; assert settings.ADMINCORE_BUILD_PROFILE=="minimal"; assert all(importlib.util.find_spec(name) is None for name in '+packages+' + '+development_packages+'); print("trimmed")') == 'trimmed')
        check('精简镜像保留全部正向迁移且空库已应用', '[ ]' not in compose('minimal', 'exec', '-T', 'backend', 'python', 'manage.py', 'showmigrations', '--plan').stdout)
        token = api('auth/login/', method='POST', data={'username':'admin','password':password}).json()['access']
        api('auth/change_password/', token, 'POST', {'old_password':password,'new_password':changed,'new_password2':changed})
        token = api('auth/login/', method='POST', data={'username':'admin','password':changed}).json()['access']
        check('精简契约关闭全部可选模块', all(not row['enabled'] for row in api('modules/',token).json()['data']['modules']))
        for endpoint in ['files/','tasks/','notifications/','approvals/','system/config/']:
            api(endpoint,token,expected=404)
        for endpoint in ['users/','permissions/roles/','permissions/menus/','logs/operation/']:
            api(endpoint,token)
        for endpoint in ['users/','permissions/roles/','logs/operation/']:
            data = api(endpoint+'?page_size=100',token).json()['data']
            check(endpoint+' 返回实际生效分页容量',data['pagination']['page_size']==100 and len(data['items'])<=100)
        snippet("from django.contrib.auth import get_user_model; from apps.files.models import FileModel; from django.core.files.base import ContentFile; from apps.core.models import SystemConfig; get_user_model().objects.create_user(username='minimal_retained',email='retained@example.test',password=None); FileModel.objects.create(original_name='retained.txt',file_type='txt',size=7,md5='0'*32,uploader=get_user_model().objects.get(username='admin'),file=ContentFile(b'fixture',name='retained.txt')); SystemConfig.objects.update_or_create(key='brand.name',defaults={'value':'精简迁移保留'})")
        original = snippet(retained)
        (FOLDER / 'browser-access.json').write_text(json.dumps({'password':changed}),encoding='utf-8')
        browser('minimal'); check('精简桌面/窄屏真实登录与核心页面，无被裁剪入口/资产')
        preview = json.loads(compose('minimal','exec','-T','backend','python','manage.py','check_modules','--modules=files').stdout)
        check('只读预检明确指出需要完整重建', preview['requires_full_build'] and preview['build_profile']=='minimal')
        for extra in [('ADMINCORE_MODULES=files',), ('ADMINCORE_STORAGE_BACKEND=s3',), ('ADMINCORE_IMAGE_PROCESSING_ENABLED=True',)]:
            arguments = ['run','--rm','--no-deps']
            for value in extra: arguments += ['-e',value]
            rejected = compose('minimal', *arguments, 'backend','python','manage.py','check',allowed_failure=True)
            check('精简镜像拒绝 '+extra[0].split('=')[0], rejected.returncode != 0 and '重新构建完整镜像' in rejected.stdout+rejected.stderr and 'ModuleNotFoundError' not in rejected.stdout+rejected.stderr)
        minimal_image = json.loads(run(['docker','image','inspect',PROJECT+'-backend']).stdout)[0]
        report['minimal_backend_bytes'] = minimal_image['Size']
        compose('full','build','backend')
        compose('full','up','-d','--wait','--wait-timeout','150','db','redis','backend')
        ready()
        browser('mismatch'); check('精简前端遇到完整模块契约明确阻止加载并提示同步重建')
        compose('full','build','frontend')
        compose('full','up','-d','--wait','--wait-timeout','150','frontend')
        ready()
        check('完整重建后恢复重依赖', snippet('import importlib.util; assert settings.ADMINCORE_BUILD_PROFILE=="full"; assert all(importlib.util.find_spec(name) for name in '+packages+'); print("restored")', 'full')=='restored')
        check('完整生产镜像仍不包含开发工具', snippet('import importlib.util; assert all(importlib.util.find_spec(name) is None for name in '+development_packages+'); print("isolated")', 'full')=='isolated')
        check('完整镜像重启迁移保留账号/文件字节/版本/品牌/迁移记录',snippet(retained,'full')==original)
        check('原密码在完整镜像重新登录', api('auth/login/',method='POST',data={'username':'admin','password':changed}).status_code==200)
        browser('full'); check('完整重建恢复可选页面和资产')
        report['full_backend_bytes'] = json.loads(run(['docker','image','inspect',PROJECT+'-backend']).stdout)[0]['Size']
        check('精简后端镜像实际缩小',report['minimal_backend_bytes']<report['full_backend_bytes'])
        compose('minimal','build','backend','frontend')
        compose('minimal','up','-d','--wait','--wait-timeout','150','backend','frontend')
        ready()
        compose('full','stop','redis')
        check('再次裁剪保留完整启用期间的所有原数据',snippet(retained)==original)
        report['passed'] = True
    finally:
        report['checks'] = CHECKS
        if report['passed']:
            compose('full','down','-v','--remove-orphans')
            run(['docker','image','rm',PROJECT+'-backend',PROJECT+'-frontend'])
            for name in ['fixture.env','browser-access.json']: (FOLDER/name).unlink(missing_ok=True)
            report['cleaned'] = ['isolated containers and volumes','isolated image tags','fixture credentials']
        else:
            compose('full','logs','--no-color',allowed_failure=True)
            compose('full','stop',allowed_failure=True)
        (FOLDER/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'evidence':str(FOLDER),**report},ensure_ascii=False),flush=True)


if __name__ == '__main__': main()
