"""从实际定义生成并安装三个模块，在独立测试配置中验收；不接触现有业务库。"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import secrets
import socket
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep', action='store_true', help='保留成功的源码副本供浏览器验收')
    parser.add_argument('--postgres', action='store_true', help='使用本任务独占的PostgreSQL容器验证真实约束和并发')
    parser.add_argument('--browser', action='store_true', help='在独占端口和前端副本中运行真实浏览器验收')
    parser.add_argument('--integrations', action='store_true', help='验收第三阶段业务审批、条件流程和报表集成')
    parser.add_argument('--business-io', action='store_true', help='验收单表业务导入导出闭环')
    parser.add_argument('--coverage-all', action='store_true', help='采集所有应用覆盖率供后端回归合并，最终门禁在合并后执行')
    args = parser.parse_args()
    folder = ROOT / '.codex-validation' / ('codegen-v2-' + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    work = folder / 'generated'
    work.mkdir()
    clean_env = {key: value for key, value in os.environ.items() if not key.startswith(('ADMINCORE_', 'DJANGO_')) and key not in {'DATABASE_URL', 'REDIS_URL', 'SECRET_KEY'}}
    temp = folder / 'test-temp'; temp.mkdir()
    env = {**clean_env, 'PYTHON_DOTENV_DISABLED': '1', 'TEMP': str(temp), 'TMP': str(temp),
           'COVERAGE_FILE': str(folder / '.coverage'), 'DJANGO_ENV': 'testing', 'PYTHONUTF8': '1',
           'PYTHONPATH': str(folder) + os.pathsep + str(ROOT / 'backend')}
    if args.integrations:
        env['ADMINCORE_INTEGRATION_EXAMPLES'] = str(ROOT / 'examples/business-integration')
        env['ADMINCORE_STAGE3'] = '1'
    if args.business_io:
        env['ADMINCORE_BUSINESS_IO'] = '1'
    report = {'passed': False, 'checks': []}
    container = None
    container_started = False

    def run(arguments, log):
        result = subprocess.run([sys.executable, *arguments], cwd=ROOT / 'backend', env=env, capture_output=True, text=True, encoding='utf-8')
        (folder / log).write_text(result.stdout + result.stderr, encoding='utf-8')
        print(result.stdout[-1500:] + result.stderr[-1500:], flush=True)
        if result.returncode:
            raise RuntimeError('验收失败，日志：' + str(folder / log))
        report['checks'].append(log)

    try:
        database_settings = ''
        if args.postgres:
            container = 'admincore-cgv2-' + folder.name.removeprefix('codegen-v2-')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
            password = secrets.token_urlsafe(40)
            env_file = folder / 'postgres.env'
            env_file.write_text('POSTGRES_DB=codegen_v2\nPOSTGRES_PASSWORD=' + password + '\n', encoding='utf-8')
            result = subprocess.run(['docker', 'run', '-d', '--name', container, '--env-file', str(env_file), '-p', f'127.0.0.1:{port}:5432', 'postgres:18.6'], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError('独立PostgreSQL启动失败：' + result.stderr)
            container_started = True
            for _ in range(60):
                ready = subprocess.run(['docker', 'exec', container, 'psql', '-U', 'postgres', '-d', 'codegen_v2', '-Atc', 'SELECT 1'], capture_output=True)
                if ready.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError('独立PostgreSQL未就绪')
            env['ADMINCORE_CODEGEN_PG_PASSWORD'] = password
            database_settings = "\nDATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'codegen_v2', 'USER': 'postgres', 'PASSWORD': __import__('os').environ['ADMINCORE_CODEGEN_PG_PASSWORD'], 'HOST': '127.0.0.1', 'PORT': %d}}\n" % port
            report['database'] = 'postgresql'
        for filename in ['suppliers.json', 'categories.json', 'purchase-orders.json']:
            source = ROOT / 'examples/codegen-v2' / filename
            if args.integrations and filename == 'purchase-orders.json':
                source = ROOT / 'examples/business-integration' / filename
            if filename == 'purchase-orders.json':
                # 真实生成主/明细两种附件外键，验证隐藏反向关系与审批历史保护。
                definition = json.loads(source.read_text(encoding='utf-8'))
                definition['details'][0]['fields'].append({
                    'name': 'evidence', 'label': '明细附件', 'kind': 'file', 'required': False,
                })
                source = folder / 'purchase-orders-reference-fixture.json'
                source.write_text(json.dumps(definition, ensure_ascii=False), encoding='utf-8')
            plan = folder / (filename + '.plan.json')
            common = ['manage.py', 'generate_module', '--definition', str(source), '--output', str(work)]
            run([*common, '--plan', str(plan)], filename + '.preview.log')
            selected = [argument for row in json.loads(plan.read_text(encoding='utf-8'))['entries'] for argument in ['--select', row['path']]]
            run([*common, '--apply-plan', str(plan), *selected], filename + '.apply.log')
        settings = f'''from config.settings.testing import *
import apps
apps.__path__.append({str(work / 'backend/apps')!r})
from apps.core import modules
from apps.cg_suppliers.manifest import MODULE as SUPPLIERS
from apps.cg_categories.manifest import MODULE as CATEGORIES
from apps.cg_orders.manifest import MODULE as ORDERS
modules.MODULES = (*modules.MODULES, SUPPLIERS, CATEGORIES, ORDERS)
INSTALLED_APPS = [*INSTALLED_APPS, 'apps.cg_suppliers', 'apps.cg_categories', 'apps.cg_orders']
ADMINCORE_MODULES = ('system', 'files', 'tasks', 'data_io', 'api_credentials', 'cg_suppliers', 'cg_categories', 'cg_orders')
MIGRATION_MODULES = {{'core': 'codegen_core_migrations'}}
'''
        if args.integrations:
            settings += "\nADMINCORE_MODULES = (*ADMINCORE_MODULES, 'organization', 'approvals', 'notifications', 'reports', 'online_forms')\n"
        if args.business_io:
            settings += "\nADMINCORE_MODULES = (*ADMINCORE_MODULES, 'tasks', 'data_io')\n"
        shutil.copytree(ROOT / 'backend/apps/core/migrations', folder / 'codegen_core_migrations', ignore=shutil.ignore_patterns('__pycache__'))
        (folder / 'codegen_v2_settings.py').write_text(settings + database_settings, encoding='utf-8')
        run(['manage.py', 'makemigrations', 'cg_suppliers', 'cg_categories', 'cg_orders', '--settings=codegen_v2_settings'], 'migrations.log')
        tests = folder / 'tests'; tests.mkdir()
        shutil.copyfile(ROOT / 'backend/tests/conftest.py', tests / 'conftest.py')
        shutil.copyfile(ROOT / 'scripts/codegen_v2_acceptance_tests.py', tests / 'test_generated.py')
        shutil.copyfile(ROOT / 'scripts/list_workbench_acceptance_tests.py', tests / 'test_list_workbench.py')
        shutil.copyfile(ROOT / 'scripts/business_search_acceptance_tests.py', tests / 'test_business_search.py')
        shutil.copyfile(ROOT / 'scripts/business_gateway_acceptance_tests.py', tests / 'test_business_gateway.py')
        shutil.copyfile(ROOT / 'backend/tests/test_file_library.py', tests / 'test_file_library.py')
        shutil.copyfile(ROOT / 'backend/tests/test_file_references.py', tests / 'test_file_references.py')
        shutil.copyfile(ROOT / 'backend/tests/test_file_documents.py', tests / 'test_file_documents.py')
        if args.integrations:
            shutil.copyfile(ROOT / 'scripts/online_form_relations_acceptance_tests.py', tests / 'test_online_form_relations.py')
            shutil.copyfile(ROOT / 'scripts/business_integration_acceptance_tests.py', tests / 'test_business_integration.py')
            shutil.copyfile(ROOT / 'backend/tests/test_report_detail_aggregation.py', tests / 'test_report_detail_aggregation.py')
            shutil.copyfile(ROOT / 'backend/tests/test_report_comparison.py', tests / 'test_report_comparison.py')
            shutil.copyfile(ROOT / 'backend/tests/test_organization_appointments.py', tests / 'test_organization_appointments.py')
            shutil.copyfile(ROOT / 'backend/tests/test_approval_operations.py', tests / 'test_approval_operations.py')
            shutil.copyfile(ROOT / 'backend/tests/test_approval_notification_write_authorization.py', tests / 'test_approval_notification_write_authorization.py')
            shutil.copyfile(ROOT / 'backend/tests/test_permission_write_authorization.py', tests / 'test_permission_write_authorization.py')
        if args.business_io:
            shutil.copyfile(ROOT / 'scripts/service_identity_acceptance_tests.py', tests / 'test_service_identity.py')
            shutil.copyfile(ROOT / 'scripts/business_io_acceptance_tests.py', tests / 'test_business_io.py')
            shutil.copyfile(ROOT / 'scripts/business_documents_acceptance_tests.py', tests / 'test_business_documents.py')
            shutil.copyfile(ROOT / 'scripts/business_exports_acceptance_tests.py', tests / 'test_business_exports.py')
        generated_tests = work / 'backend/tests'
        for path in generated_tests.glob('test_generated_*.py'):
            shutil.copyfile(path, tests / path.name)
        run(['-m', 'pytest', str(tests), '-c', str(ROOT / 'backend/pytest.ini'), '--ds=codegen_v2_settings', '--create-db', '--basetemp', str(folder / 'pytest-tmp'),
             '--junitxml=' + str(folder / 'integration.xml'), '--cov=' + ('apps' if args.coverage_all else 'apps.core.codegen.runtime'),
             '--cov-fail-under=' + ('0' if args.coverage_all else '90'), '--cov-report=term-missing', '--cov-report=json:' + str(folder / 'runtime-coverage.json'), '-q'], 'integration.log')
        run(['manage.py', 'spectacular', '--settings=codegen_v2_settings', '--validate', '--fail-on-warn', '--file', str(folder / 'schema.yml')], 'schema.log')
        if args.browser:
            from codegen_v2_browser_fixture import validate_browser
            validate_browser(folder, work, env)
            report['checks'].append('browser-fixture-report.json')
        report['passed'] = True
    finally:
        (folder / 'postgres.env').unlink(missing_ok=True)
        if container_started:
            logs = subprocess.run(['docker', 'logs', container], capture_output=True, text=True)
            (folder / 'postgres.log').write_text(logs.stdout + logs.stderr, encoding='utf-8')
            subprocess.run(['docker', 'rm', '-f', '-v', container] if report['passed'] else ['docker', 'stop', container], capture_output=True, check=True)
            report['postgres_container'] = container
            report['postgres_removed'] = report['passed']
        if report['passed'] and not args.keep:
            if work.resolve().parent != folder.resolve() or not folder.name.startswith('codegen-v2-'):
                raise RuntimeError('清理路径不符合任务边界')
            shutil.rmtree(work)
            report['cleaned'] = [str(work)]
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'evidence': str(folder), **report}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
