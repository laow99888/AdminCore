"""真实生成代码安装验收：隔离源代码、PostgreSQL、Redis、Nginx和浏览器。

不修改原项目注册、正式数据或凭据；成功只删除本脚本的工作副本/容器/凭据。
"""
from pathlib import Path
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
import requests

ROOT = Path(__file__).resolve().parents[1]
NODE_BIN = ROOT / '.codex-validation' / 'toolchains' / 'node-v24.21.0-win-x64'
PROJECT = 'admincore-codegen-' + uuid.uuid4().hex[:8]
FOLDER = ROOT / '.codex-validation' / PROJECT
WORK = FOLDER / 'workspace'
BASE = 'http://127.0.0.1:18451/api/v1/'
CHECKS = []


def run(arguments, *, cwd=ROOT, input=None, allowed_failure=False, env=None):
    result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, input=input,
        encoding='utf-8', errors='replace', timeout=600, env=env)
    with (FOLDER / 'contract.log').open('a', encoding='utf-8') as log:
        log.write(result.stdout + result.stderr)
    if result.returncode and not allowed_failure:
        raise RuntimeError('隔离验收命令失败，见contract.log')
    return result


def compose(*arguments, input=None, allowed_failure=False):
    return run(['docker', 'compose', '-p', PROJECT, '--env-file', str(FOLDER / 'fixture.env'),
        '-f', str(FOLDER / 'compose.yml'), *arguments], input=input, allowed_failure=allowed_failure)


def check(label, condition=True):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label); print('通过：' + label, flush=True)


def snippet(code):
    prefix = "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); import django; django.setup(); from django.conf import settings; assert settings.DATABASES['default']['NAME']=='codegen_fixture'\n"
    return compose('exec', '-T', 'backend', 'python', '-c', 'import sys; exec(sys.stdin.read())', input=prefix + code).stdout.strip()


def api(path, token=None, method='GET', data=None, expected=200, headers=None):
    response = requests.request(method, BASE + path, json=data,
        headers={**({'Authorization': 'Bearer ' + token} if token else {}), **(headers or {})}, timeout=15)
    check(method + ' ' + path + ' → ' + str(expected), response.status_code == expected)
    return response


def backend_command(*arguments):
    return run([sys.executable, '-X', 'utf8', 'manage.py', *arguments], cwd=WORK / 'backend',
        env={**os.environ, 'DJANGO_SETTINGS_MODULE': 'config.settings.testing', 'DJANGO_ENV': 'testing'})


def existing_table_acceptance(token):
    # 从真实元数据生成第二模块，在原隔离表上运行managed=False CRUD。
    output = snippet("""import json
from apps.core.codegen.tables import inspect_table
from apps.core.codegen.spec import parse_definition
from apps.core.codegen.render import render
from apps.core.codegen.plans import make_plan, apply_plan
from pathlib import Path
definition=inspect_table('work_assets_assetrecord','catalog_items','CatalogItem','目录记录')
root=Path('/tmp/generated-table-review'); files=render(parse_definition(definition))
apply_plan(root,make_plan(root,definition,files),definition,files,list(files))
print(json.dumps(definition,ensure_ascii=False))
""")
    inferred = json.loads(output)
    check('已有表整数约束被识别而非放宽', next(row for row in inferred['fields'] if row['name'] == 'quantity')['maximum'] == 100)
    transfer = FOLDER / 'table-generated'
    compose('cp', 'backend:/tmp/generated-table-review', str(transfer))
    for name in ['backend', 'frontend', 'docs']:
        shutil.copytree(transfer / name, WORK / name, dirs_exist_ok=True)
    modules = WORK / 'backend/apps/core/modules.py'
    modules.write_text(modules.read_text(encoding='utf-8').replace('PRESETS =',
        "from apps.catalog_items.manifest import MODULE as TABLE_MODULE\nMODULES = (*MODULES, TABLE_MODULE)\nPRESETS =", 1), encoding='utf-8')
    settings = WORK / 'backend/config/settings/base.py'
    settings.write_text(settings.read_text(encoding='utf-8').replace("    'apps.work_assets',", "    'apps.work_assets',\n    'apps.catalog_items',", 1), encoding='utf-8')
    registry = WORK / 'frontend/src/modules/registry.ts'
    registry.write_text(registry.read_text(encoding='utf-8').replace('}] as const', "}, { key: 'catalog_items', path: '/catalog-items', permission: 'catalog_items:read', title: '目录记录', component: () => import('../views/catalog_items/RecordListView.vue') }] as const"), encoding='utf-8')
    backend_command('makemigrations', 'catalog_items', 'core')
    run([sys.executable, '-X', 'utf8', '-m', 'pytest', 'tests/test_generated_catalog_items.py'], cwd=WORK / 'backend')
    backend_command('spectacular', '--validate', '--fail-on-warn', '--file', str(FOLDER / 'two-module-schema.yml'))
    check('第二个已有表生成模块的测试及双模块OpenAPI无冲突')
    env_file = FOLDER / 'fixture.env'
    env_file.write_text(env_file.read_text(encoding='utf-8').replace('ADMINCORE_MODULES=work_assets\n', 'ADMINCORE_MODULES=work_assets,catalog_items\n'), encoding='utf-8')
    compose('build', 'backend', 'frontend')
    compose('up', '-d', '--wait', '--wait-timeout', '180')
    values = {'label': '已有表新增', 'remarks': '不重建旧表', 'quantity': 8, 'available': False, 'version': 0}
    created = api('catalog-items/records/', token, 'POST', values, 201).json()['data']
    detail = 'catalog-items/records/' + created['id'] + '/'
    api(detail, token, 'PATCH', {'version': 1, 'quantity': 101}, 400)
    api(detail, token, 'PATCH', {'version': 1, 'quantity': 9})
    check('managed=False真实写入原表且保留版本与字段界限', snippet("from apps.work_assets.models import AssetRecord; from apps.catalog_items.models import CatalogItem; assert not CatalogItem._meta.managed; row=AssetRecord.objects.get(label='已有表新增'); assert row.version==2 and row.quantity==9; print('preserved')") == 'preserved')
    api(detail, token, 'DELETE', {'version': 2})
    compose('exec', '-T', 'backend', 'python', 'manage.py', 'makemigrations', '--check', '--dry-run')
    check('两个生成模块均无遗漏迁移，已有表没有重复创建')
    snippet("""from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from rest_framework.test import APIClient
from drf_spectacular.generators import SchemaGenerator
from apps.work_assets.views import RecordViewSet as NewTableView
from apps.catalog_items.views import RecordViewSet as ExistingTableView
client=APIClient(HTTP_HOST='localhost')
client.force_authenticate(get_user_model().objects.get(username='admin'))
with connection.cursor() as cursor:
    cursor.execute("SELECT name, setting FROM pg_settings WHERE name IN ('statement_timeout','lock_timeout')")
    original=dict(cursor.fetchall())
def slow_query(view):
    with connection.cursor() as cursor: cursor.execute('SELECT pg_sleep(1)')
    raise AssertionError('数据库没有取消慢SQL')
with override_settings(ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS=100):
    for view,path in [(NewTableView,'/api/v1/work-assets/records/'),(ExistingTableView,'/api/v1/catalog-items/records/')]:
        with patch.object(view,'get_queryset',slow_query):
            response=client.get(path)
        assert response.status_code==503 and response.json()=={'code':503,'message':'查询超时或等待锁过久，请缩小筛选范围后重试','data':None}
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, setting FROM pg_settings WHERE name IN ('statement_timeout','lock_timeout')")
            assert dict(cursor.fetchall())==original
        assert client.get(path).status_code==200
        response_schema=SchemaGenerator().get_schema(request=None,public=True)['paths'][path]['get']['responses']
        assert set(response_schema)>={'200','400','503'}
        assert 'Paginated' in response_schema['200']['content']['application/json']['schema']['$ref']
        with patch.object(view,'get_queryset',side_effect=AssertionError('无效查询不应访问资源')):
            for query in ['?unknown=1','?ordering=creator__username','?ordering=created_at,-created_at','?page=1&page=2']:
                assert client.get(path+query).status_code==400
        assert client.get(path,{'ordering':'created_at','page_size':2}).status_code==200
print('generated budgets verified')
""")
    check('两个生成模块真实慢SQL取消、连接恢复、查询白名单及200/400/503分页OpenAPI通过')


def main():
    for port in [18450, 18451]:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    FOLDER.mkdir(parents=True); WORK.mkdir()
    common_ignored = shutil.ignore_patterns('venv', '.venv', '__pycache__', '.pytest_cache', 'node_modules',
        'dist', 'coverage', 'test-results', 'playwright-report', '.env', '*.sqlite3')
    def ignored(folder, names):
        excluded = set(common_ignored(folder, names))
        if Path(folder).resolve() == (ROOT / 'backend').resolve():
            excluded.update({'media', 'logs', 'staticfiles'} & set(names))
        return excluded
    for name in ['backend', 'frontend']:
        shutil.copytree(ROOT / name, WORK / name, ignore=ignored)
    # 截断python-dotenv向父目录查找，副本不继承原项目.env。
    (WORK / '.env').write_text('# isolated validation only\n', encoding='utf-8')
    raw = {'module': 'work_assets', 'title': '资产记录', 'model': 'AssetRecord', 'fields': [
        {'name': 'label', 'label': '名称', 'kind': 'string', 'max_length': 80},
        {'name': 'remarks', 'label': '备注', 'kind': 'text', 'required': False},
        {'name': 'quantity', 'label': '数量', 'kind': 'integer', 'minimum': 0, 'maximum': 100},
        {'name': 'available', 'label': '可用', 'kind': 'boolean', 'default': True}]}
    definition = FOLDER / 'definition.json'; plan = FOLDER / 'plan.json'
    definition.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    backend_command('generate_module', '--definition', str(definition), '--output', str(WORK), '--plan', str(plan))
    selected = [row['path'] for row in json.loads(plan.read_text(encoding='utf-8'))['entries']]
    arguments = ['generate_module', '--definition', str(definition), '--output', str(WORK), '--apply-plan', str(plan)]
    for name in selected:
        arguments += ['--select', name]
    backend_command(*arguments)
    check('通过管理命令从预览计划生成十二个真实文件', len(selected) == 12)
    modules = WORK / 'backend/apps/core/modules.py'
    content = modules.read_text(encoding='utf-8').replace('PRESETS =',
        "from apps.work_assets.manifest import MODULE as GENERATED_MODULE\nMODULES = (*MODULES, GENERATED_MODULE)\nPRESETS =", 1)
    modules.write_text(content, encoding='utf-8')
    settings = WORK / 'backend/config/settings/base.py'
    settings.write_text(settings.read_text(encoding='utf-8').replace("    'apps.example',", "    'apps.example',\n    'apps.work_assets',", 1), encoding='utf-8')
    registry = WORK / 'frontend/src/modules/registry.ts'
    registry.write_text(registry.read_text(encoding='utf-8').replace('}] as const', "}, { key: 'work_assets', path: '/work-assets', permission: 'work_assets:read', title: '资产记录', component: () => import('../views/work_assets/RecordListView.vue') }] as const"), encoding='utf-8')
    backend_command('makemigrations', 'work_assets', 'core')
    run([sys.executable, '-X', 'utf8', '-m', 'pytest', 'tests/test_generated_work_assets.py'], cwd=WORK / 'backend')
    backend_command('spectacular', '--validate', '--fail-on-warn', '--file', str(FOLDER / 'generated-schema.yml'))
    check('生成代码权限/CRUD/事务/列表查询用例及严格OpenAPI通过')
    password = secrets.token_urlsafe(40)
    env_file = FOLDER / 'fixture.env'
    environment = {'DJANGO_SECRET_KEY': secrets.token_urlsafe(60), 'DB_PASSWORD': secrets.token_urlsafe(40),
        'DB_NAME': 'codegen_fixture', 'DB_USER': 'postgres', 'DB_HOST': 'db', 'DJANGO_ENV': 'production',
        'DJANGO_DEBUG': 'False', 'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend',
        'ADMINCORE_ADMIN_PASSWORD': password, 'AUTH_LOGIN_CAPTCHA_ENABLED': 'False',
        'REDIS_URL': 'redis://redis:6379/0', 'ADMINCORE_MODULES': 'work_assets', 'USE_TLS': 'False'}
    env_file.write_text(''.join(key + '=' + value + '\n' for key, value in environment.items()), encoding='utf-8')
    compose_data = {'services': {
        'db': {'image': 'postgres:18.6', 'environment': {'POSTGRES_DB': '${DB_NAME}', 'POSTGRES_USER': 'postgres', 'POSTGRES_PASSWORD': '${DB_PASSWORD}'},
            'volumes': ['pgdata:/var/lib/postgresql'], 'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U postgres -d codegen_fixture'], 'interval': '2s', 'timeout': '3s', 'retries': 30}},
        'redis': {'image': 'redis:8.10.2'},
        'backend': {'build': str(WORK / 'backend'), 'image': PROJECT + '-backend', 'env_file': [str(env_file)],
            'ports': ['127.0.0.1:18450:8000'], 'depends_on': {'db': {'condition': 'service_healthy'}, 'redis': {'condition': 'service_started'}},
            'healthcheck': {'test': ['CMD', 'python', '/app/docker/healthcheck.py'], 'interval': '3s', 'timeout': '5s', 'retries': 40}},
        'frontend': {'build': str(WORK / 'frontend'), 'image': PROJECT + '-frontend', 'ports': ['127.0.0.1:18451:80'],
            'depends_on': {'backend': {'condition': 'service_healthy'}}}}, 'volumes': {'pgdata': {}}}
    (FOLDER / 'compose.yml').write_text(json.dumps(compose_data, indent=2), encoding='utf-8')
    report = {'passed': False, 'project': PROJECT, 'ports': [18450, 18451]}
    try:
        # 源码副本独立安装锁定依赖，避免目录联接影响原node_modules。
        bundled = os.name == 'nt' and (NODE_BIN / 'node.exe').exists()
        node = str(NODE_BIN / 'node.exe') if bundled else shutil.which('node')
        npm = [node, str(NODE_BIN / 'node_modules/npm/bin/npm-cli.js')] if bundled else [shutil.which('npm')]
        node_env = {**os.environ, 'PATH': (str(NODE_BIN) + os.pathsep if bundled else '') + os.environ.get('PATH', '')}
        run([*npm, 'ci', '--ignore-scripts'], cwd=WORK / 'frontend', env=node_env)
        run([*npm, 'run', 'lint'], cwd=WORK / 'frontend', env=node_env)
        run([*npm, 'run', 'build'], cwd=WORK / 'frontend', env=node_env)
        check('生成页面在原设计系统下lint/类型/构建通过')
        compose('build', 'backend', 'frontend')
        compose('up', '-d', '--wait', '--wait-timeout', '180')
        token = api('auth/login/', method='POST', data={'username': 'admin', 'password': password}).json()['access']
        changed_password = secrets.token_urlsafe(40)
        api('auth/change_password/', token, 'POST', {'old_password': password, 'new_password': changed_password, 'new_password2': changed_password})
        token = api('auth/login/', method='POST', data={'username': 'admin', 'password': changed_password}).json()['access']
        caps = api('modules/', token).json()['data']['modules']
        check('真实模块注册与权限页面同步', next(item for item in caps if item['key'] == 'work_assets')['page_permissions'] == {'/work-assets': 'work_assets:read'})
        values = {'label': '隔离资产', 'remarks': '<script>正文只作文字</script>', 'quantity': 2, 'available': True, 'version': 0}
        first = api('work-assets/records/', token, 'POST', values, 201, {'Idempotency-Key': 'generated-http-once'})
        second = api('work-assets/records/', token, 'POST', values, 201, {'Idempotency-Key': 'generated-http-once'})
        check('真实PostgreSQL创建幂等且只产生一个审计', first.json() == second.json() and second.headers['Idempotency-Replayed'] == 'true')
        row = first.json()['data']; detail = 'work-assets/records/' + row['id'] + '/'
        api(detail, token, 'PATCH', {'version': 0, 'quantity': 3}, 409)
        api(detail, token, 'PATCH', {'version': 1, 'quantity': 101}, 400)
        api(detail, token, 'PATCH', {'version': 1, 'quantity': 3})
        check('数据库字段界限、版本和审计摘要', snippet("from apps.work_assets.models import AssetRecord; from apps.logs.models import OperationLog; assert AssetRecord.objects.count()==1; assert AssetRecord.objects.get().version==2; logs=OperationLog.objects.filter(resource='work_assets'); assert logs.count()==2; assert all('隔离资产' not in str(row.after_values) and '正文' not in str(row.after_values) for row in logs); print('safe')") == 'safe')
        compose('exec', '-T', 'backend', 'python', 'manage.py', 'spectacular', '--validate', '--fail-on-warn', '--file', '/tmp/generated-schema.yml')
        check('真实部署启用生成模块的OpenAPI无警告')
        # 真实SQL元数据识别，不能以SQLite或模板解析代替已有表接入。
        snippet("from django.db import connection; from apps.work_assets.models import AssetRecord; from apps.core.codegen.tables import inspect_table,verify_table; from apps.core.codegen.spec import parse_definition; result=inspect_table(AssetRecord._meta.db_table,'catalog_items','CatalogItem','目录记录'); assert len(result['fields'])==4; verify_table(parse_definition(result)); print('inspected')")
        check('已有PostgreSQL业务表只读识别并复核四类字段')
        snippet("""from django.db import connection
from apps.core.codegen.tables import inspect_table
from apps.core.codegen.spec import GenerationError
for name in ['users_user','missing_business_table']:
    try: inspect_table(name,'catalog_items','CatalogItem','目录记录')
    except GenerationError: pass
    else: raise AssertionError('内部/缺失表不应生成')
with connection.cursor() as cursor:
    cursor.execute('CREATE TABLE fixture_complex_table (LIKE work_assets_assetrecord INCLUDING ALL)')
try:
    try: inspect_table('fixture_complex_table','catalog_items','CatalogItem','目录记录')
    except GenerationError: pass
    else: raise AssertionError('无创建者外键的复制表不应生成')
finally:
    with connection.cursor() as cursor: cursor.execute('DROP TABLE fixture_complex_table')
print('rejected')
""")
        check('内部表/不存在表/无创建者关联的表均拒绝生成')
        # 浏览器脚本仅获得本次隔离密码，报告不含凭据。
        (FOLDER / 'browser-access.json').write_text(json.dumps({'password': changed_password}), encoding='utf-8')
        script = ROOT / 'scripts/codegen_browser.mjs'
        run([node, str(script), str(WORK / 'frontend'), str(FOLDER)], cwd=ROOT, env=node_env)
        check('桌面和手机真实登录/表单/版本冲突/恢复/详情文本验收')
        snippet((ROOT / 'scripts/codegen_concurrency.py').read_text(encoding='utf-8'))
        check('生成模块真实SQL并发/幂等/删除及四类等待撤权通过')
        api(detail, token, 'DELETE', {'version': 1}, 409)
        current = api(detail, token).json()['data']['version']
        api(detail, token, 'DELETE', {'version': current})
        existing_table_acceptance(token)
        report['passed'] = True
    finally:
        report['checks'] = CHECKS
        if report['passed']:
            compose('down', '-v', '--remove-orphans')
            for name in ['fixture.env', 'browser-access.json']:
                (FOLDER / name).unlink(missing_ok=True)
            if WORK.resolve().parent != FOLDER.resolve() or not FOLDER.name.startswith('admincore-codegen-'):
                raise RuntimeError('工作副本清理边界不正确')
            shutil.rmtree(WORK)
            transfer = FOLDER / 'table-generated'
            if transfer.exists():
                if transfer.resolve().parent != FOLDER.resolve() or transfer.is_symlink():
                    raise RuntimeError('已有表产物清理边界不正确')
                shutil.rmtree(transfer)
            report['cleaned'] = ['isolated containers and volumes', 'fixture credentials', str(WORK)]
        else:
            compose('logs', '--no-color', allowed_failure=True)
            compose('stop', allowed_failure=True)
        (FOLDER / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(FOLDER), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
