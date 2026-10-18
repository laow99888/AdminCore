"""以隔离的最小 Django 底座和真实业务数据库验收连续两次升级；不触及生产项目。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile

from create_project import REQUIRED, create_project, load_project, upgrade_plan


SCRIPTS = Path(__file__).resolve().parent


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_temporary(path):
    assert path.parent == Path(tempfile.gettempdir()).resolve() and path.name.startswith('admincore-project-upgrades-')

    def writable_retry(function, failed_path, error):
        if not isinstance(error, PermissionError):
            raise error
        os.chmod(failed_path, stat.S_IWRITE | stat.S_IREAD)
        function(failed_path)

    shutil.rmtree(path, onexc=writable_retry)


def run(argv, cwd, log, *, success=True):
    # Drop host Django/database credentials; fixtures read their own .env only.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(('DJANGO_', 'ADMINCORE_'))
                   and key not in {'DATABASE_URL', 'DATABASE_NAME', 'PYTHONPATH', 'SECRET_KEY'}}
    environment.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([str(value) for value in argv], cwd=cwd, env=environment,
                            capture_output=True, encoding='utf-8', errors='replace', timeout=180)
    with log.open('a', encoding='utf-8') as output:
        output.write(result.stdout + result.stderr)
    if success and result.returncode:
        raise RuntimeError(f'验收命令失败，详见 {log.name}')
    if not success and result.returncode == 0:
        raise RuntimeError('预期失败的验收命令意外成功')
    return result.stdout


def commit(source, log, message):
    run(['git', 'add', '.'], source, log)
    run(['git', 'commit', '-m', message], source, log)
    return run(['git', 'rev-parse', 'HEAD'], source, log).strip()


def foundation_model(stage):
    value = 'from django.db import models\nclass BaseItem(models.Model):\n    code=models.CharField(max_length=32,unique=True)\n'
    if stage >= 1:
        value += '    release_code=models.CharField(max_length=16,default="B")\n'
    if stage >= 2:
        value += '    revision=models.PositiveIntegerField(default=2)\n'
    return value


def build_source(source, log):
    source.mkdir()
    for path in REQUIRED:
        write(source, path, '# isolated upgrade fixture\n')
    write(source, '.gitignore', '__pycache__/\n*.sqlite3\n.env\n.codex-validation/\n')
    write(source, '.env.example', 'DJANGO_SECRET_KEY=placeholder\nDB_PASSWORD=placeholder\nADMINCORE_ADMIN_PASSWORD=\n')
    for name in ('create_project.py', 'project.py', 'project_upgrade.py'):
        write(source, 'scripts/' + name, (SCRIPTS / name).read_text(encoding='utf-8'))
    write(source, 'backend/manage.py', 'import os,sys\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_settings")\nfrom django.core.management import execute_from_command_line\nexecute_from_command_line(sys.argv)\n')
    write(source, 'backend/config/__init__.py', '')
    write(source, 'backend/config/base_settings.py', 'INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes", "foundation"]\nDEFAULT_AUTO_FIELD="django.db.models.BigAutoField"\nUSE_TZ=True\n')
    write(source, 'backend/foundation/__init__.py', '')
    write(source, 'backend/foundation/migrations/__init__.py', '')
    write(source, 'backend/foundation/models.py', foundation_model(0))
    write(source, 'backend/foundation/migrations/0001_initial.py', '''from django.db import migrations,models
class Migration(migrations.Migration):
    initial=True
    dependencies=[]
    operations=[migrations.CreateModel(name='BaseItem', fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('code',models.CharField(max_length=32,unique=True))])]
''')
    write(source, 'backend/config/base-version.json', json.dumps({'version': '0.1.0-fixture.a'}))
    run(['git', 'init'], source, log)
    run(['git', 'config', 'user.name', '升级隔离验收'], source, log)
    run(['git', 'config', 'user.email', 'upgrade-fixture@example.invalid'], source, log)
    return commit(source, log, '建立最小 Django 底座 A')


def business_project(project):
    write(project, 'backend/business_settings.py', '''from pathlib import Path
from config.base_settings import *
ROOT=Path(__file__).resolve().parents[1]
SECRET_KEY=next(line.split('=',1)[1] for line in (ROOT/'.env').read_text().splitlines() if line.startswith('DJANGO_SECRET_KEY='))
INSTALLED_APPS=[*INSTALLED_APPS,'business']
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':ROOT/'business.sqlite3'}}
''')
    write(project, 'backend/business/__init__.py', '')
    write(project, 'backend/business/models.py', '''from django.conf import settings
from django.db import models
class Order(models.Model):
    number=models.CharField(max_length=32,unique=True)
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    item=models.ForeignKey('foundation.BaseItem',on_delete=models.PROTECT)
    amount=models.PositiveIntegerField()
''')
    write(project, 'backend/business/migrations/__init__.py', '')
    write(project, 'backend/business/migrations/0001_initial.py', '''from django.conf import settings
from django.db import migrations,models
import django.db.models.deletion
class Migration(migrations.Migration):
    initial=True
    dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL),('foundation','0001_initial')]
    operations=[migrations.CreateModel(name='Order',fields=[('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('number',models.CharField(max_length=32,unique=True)),('amount',models.PositiveIntegerField()),('owner',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),('item',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='foundation.baseitem'))])]
''')
    write(project, 'backend/seed_business.py', '''import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','business_settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from foundation.models import BaseItem
from business.models import Order
user=get_user_model().objects.create_user(username='business-owner',password=None,first_name='业务用户')
for i in range(3):
    item=BaseItem.objects.create(code=f'ITEM-{i}')
    Order.objects.create(number=f'ORDER-{i}',owner=user,item=item,amount=12500+i)
''')
    write(project, 'backend/verify_business.py', '''import hashlib,json,os,sys
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE','business_settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from django.db.migrations.recorder import MigrationRecorder
from foundation.models import BaseItem
from business.models import Order
root=Path(__file__).resolve().parents[1]
stage=int(sys.argv[1])
expected=json.loads((root/'.codex-validation/business-baseline.json').read_text()) if stage else None
rows={'users':list(get_user_model().objects.order_by('pk').values('id','username','password','first_name','is_active')),
      'items':list(BaseItem.objects.order_by('pk').values('id','code')),
      'orders':list(Order.objects.order_by('pk').values('id','number','owner_id','item_id','amount'))}
assert len(rows['users'])==1 and len(rows['items'])==len(rows['orders'])==3
assert all(row.owner.username=='business-owner' and row.item.code.startswith('ITEM-') for row in Order.objects.select_related('owner','item'))
fingerprint=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
if expected is not None:
    assert fingerprint==expected['business_fingerprint'],'业务数据发生非预期变化'
if stage>=1:
    assert set(BaseItem.objects.values_list('release_code',flat=True))=={'migrated-B'}
if stage>=2:
    assert set(BaseItem.objects.values_list('revision',flat=True))=={20}
migrations=sorted(name for app,name in MigrationRecorder.Migration.objects.filter(app='foundation').values_list('app','name'))
assert len(migrations)==stage+1
report={'business_fingerprint':fingerprint,'counts':{key:len(value) for key,value in rows.items()},'foundation_migrations':migrations}
if stage==0:
    (root/'.codex-validation/business-baseline.json').write_text(json.dumps(report))
print(json.dumps(report))
''')


def next_source(source, stage, log):
    write(source, 'backend/foundation/models.py', foundation_model(stage))
    if stage == 1:
        path, dependency, field, declaration, update = ('0002_release', '0001_initial', 'release_code', "models.CharField(max_length=16,default='B')", "release_code='migrated-B'")
    else:
        path, dependency, field, declaration, update = ('0003_revision', '0002_release', 'revision', 'models.PositiveIntegerField(default=2)', 'revision=20')
    write(source, 'backend/foundation/migrations/' + path + '.py', f'''from django.db import migrations,models
def backfill(apps,schema_editor):
    apps.get_model('foundation','BaseItem').objects.using(schema_editor.connection.alias).update({update})
class Migration(migrations.Migration):
    dependencies=[('foundation','{dependency}')]
    operations=[migrations.AddField(model_name='baseitem',name='{field}',field={declaration}),migrations.RunPython(backfill,migrations.RunPython.noop)]
''')
    write(source, 'backend/config/base-version.json', json.dumps({'version': f'0.1.0-fixture.{"b" if stage == 1 else "c"}'}))
    return commit(source, log, f'推进 Django 底座 {stage + 1} 并迁移存量数据')


def validate(output):
    """Returns a credential-free report; leaves its own temp project only on failure."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    temporary = Path(tempfile.mkdtemp(prefix='admincore-project-upgrades-')).resolve()
    source, project = temporary / 'upstream', temporary / 'business-project'
    report = {'passed': False, 'fixture': 'minimal-django-real-migrations', 'rounds': []}
    log = output / 'commands.log'
    try:
        import django
        report['django_version'] = django.get_version()
        revision = build_source(source, log)
        # Real port checks without starting services.
        with socket.socket() as one, socket.socket() as two:
            one.bind(('127.0.0.1', 0))
            two.bind(('127.0.0.1', 0))
            ports = one.getsockname()[1], two.getsockname()[1]
        original = create_project(project, source=source, name='upgrade-fixture', frontend_port=ports[0], backend_port=ports[1])
        business_project(project)
        private = project / '.codex-validation'
        private.mkdir()
        manage = [sys.executable, 'backend/manage.py']
        run([*manage, 'migrate', '--noinput'], project, log)
        run([sys.executable, 'backend/seed_business.py'], project, log)
        data = json.loads(run([sys.executable, 'backend/verify_business.py', '0'], project, log))
        business_files = {str(path.relative_to(project)): digest(path) for path in (project / 'backend/business').rglob('*.py')}
        business_files['backend/business_settings.py'] = digest(project / 'backend/business_settings.py')
        protected = {name: digest(project / name) for name in ('.env', 'compose.project.yml')}
        report.update(initial_revision=revision, initial_data=data)
        for stage in (1, 2):
            target = next_source(source, stage, log)
            plan_file = private / f'plan-{stage}.json'
            cli = [sys.executable, 'scripts/project.py']
            run([*cli, 'upgrade-plan', '--source', source, '--output', plan_file], project, log)
            plan = json.loads(plan_file.read_text())
            assert plan['to_revision'] == target
            run([*cli, 'upgrade-apply', '--source', source, '--plan', plan_file], project, log)
            assert load_project(project)['source_revision'] == revision
            # A failed gate cannot advance baseline, even after real schema/data migration.
            checks = [[*manage, 'migrate', '--noinput'], [*manage, 'check'],
                      [*manage, 'makemigrations', '--check', '--dry-run'],
                      [sys.executable, 'backend/verify_business.py', str(stage)]]
            if stage == 1:
                failed_checks = private / 'failed-checks.json'
                failed_checks.write_text(json.dumps([*checks, [sys.executable, '-c', 'raise SystemExit(7)']]))
                run([*cli, 'upgrade-accept', '--checks', failed_checks], project, log, success=False)
                assert load_project(project)['source_revision'] == revision
                shutil.copyfile(project / '.admincore-upgrade/validation.log', output / 'failed-gate.log')
            checks_file = private / f'checks-{stage}.json'
            checks_file.write_text(json.dumps(checks))
            accepted = json.loads(run([*cli, 'upgrade-accept', '--checks', checks_file], project, log))
            metadata = load_project(project)
            assert metadata['source_revision'] == target and metadata['instance_id'] == original['instance_id']
            assert all(digest(project / name) == value for name, value in {**business_files, **protected}.items())
            assert not (project / '.admincore-upgrade').exists()
            assert not any(row['upstream_changed'] for row in upgrade_plan(project, source)['changes'])
            observed = json.loads(run([sys.executable, 'backend/verify_business.py', str(stage)], project, log))
            shutil.copyfile(project / accepted['evidence'] / 'validation.log', output / f'round-{stage}-validation.log')
            report['rounds'].append({'from_revision': revision, 'to_revision': target,
                'base_version': metadata['base_version'], **observed,
                'business_source_unchanged': True, 'environment_unchanged': True,
                'instance_unchanged': True, 'baseline_advanced_after_checks': True})
            revision = target
        report.update(passed=True, failed_gate_preserved_baseline=True, services_started=0)
    finally:
        try:
            if report['passed']:
                remove_temporary(temporary)
                report['temporary_removed'] = True
        finally:
            if temporary.exists():
                report.update(passed=False, retained_private_workspace=str(temporary))
            (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='全新证据目录；失败保留隔离工作区')
    options = parser.parse_args()
    result = validate(options.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
