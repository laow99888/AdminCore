"""仅独立 foundation PostgreSQL：Office 真实行锁/历史删除并发验收。

由 manage.py shell exec(base64bytes) 执行，不依赖 __file__。不调用 LibreOffice；
输入为有效最小 ZIP/PDF。patch 仅观察/暂停真实 SQL，同步期间不替换授权或状态操作。
全局 claim/cleanup 开始前拒绝任何既有 OfficePreview；所有媒体另存本次临时根。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import io
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Event
import types
from uuid import uuid4
import zipfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import connection, connections
from django.test import override_settings
from django.urls import include, path
from django.utils import timezone
from pypdf import PdfWriter
from rest_framework.test import APIClient

from apps.auth_app.sessions import issue_session
from apps.core.models import DataScopeGrant, Department, OrganizationMembership
from apps.files.models import FileModel, OfficePreview
from apps.files import office_preview as office
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.tasks.models import TaskRecord

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库运行'
assert connection.vendor == 'postgresql', '必须使用真实 PostgreSQL'
assert not connection.in_atomic_block, '跨连接夹具必须真实提交'
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    assert cursor.fetchone()[0] == 'foundation'
    # The coordinating connection can also touch fixture rows while A is paused.
    # Bound it too, so an old inverted lock order fails instead of hanging setup.
    cursor.execute("SET lock_timeout = '6s'")
    cursor.execute("SET statement_timeout = '12s'")
assert not OfficePreview.objects.exists(), '存在其他 Office 任务，拒绝运行全局领取/清理'

suffix = uuid4().hex[:12]
prefix = 'office_pg_' + suffix
media = Path(tempfile.mkdtemp(prefix='admincore-office-pg-' + suffix + '-')).resolve()
url_name = 'admincore_office_pg_urls_' + suffix
assert url_name not in sys.modules
urls = types.ModuleType(url_name)
urls.urlpatterns = [path('api/v1/files/', include('apps.files.urls')),
                    path('api/v1/tasks/', include('apps.tasks.urls'))]
sys.modules[url_name] = urls

User = get_user_model()
actor = User.objects.create_user(prefix + '_owner', password=uuid4().hex + uuid4().hex,
                                 must_change_password=False)
auditor = User.objects.create_user(prefix + '_history', password=uuid4().hex + uuid4().hex,
                                   must_change_password=False)
role = Role.objects.create(name=prefix)
for code in ('file:download', 'task:read', 'task:delete'):
    RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
UserRole.objects.bulk_create([UserRole(user=actor, role=role), UserRole(user=auditor, role=role)])
department = Department.objects.create(name=prefix)
OrganizationMembership.objects.bulk_create([
    OrganizationMembership(user=actor, department=department),
    OrganizationMembership(user=auditor, department=department)])
grant = DataScopeGrant.objects.create(role=role, resource='task', scope='custom')
grant.departments.add(department)
actor_token, auditor_token = issue_session(actor), issue_session(auditor)

archive = io.BytesIO()
with zipfile.ZipFile(archive, 'w') as package:
    package.writestr('[Content_Types].xml', '<Types>application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml</Types>')
    package.writestr('word/document.xml', '<root/>')
source_bytes = archive.getvalue()
stream = io.BytesIO()
writer = PdfWriter()
writer.add_blank_page(width=100, height=100)
writer.write(stream)
pdf_bytes = stream.getvalue()
own_sources, own_records, own_jobs = set(), set(), set()
checks = []


def client(token=actor_token):
    api = APIClient(HTTP_HOST='localhost')
    api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    return api


def local_only():
    assert not OfficePreview.objects.exclude(pk__in=own_jobs).exists(), '出现非本脚本Office任务'


def fixture(name, *, running=False, succeeded=False, lost=False):
    from django.core.files.base import ContentFile
    local_only()
    assert not OfficePreview.objects.filter(record__status__in=('pending', 'running')).exists()
    source = FileModel.objects.create(uploader=actor, original_name=name + '.docx',
        file_type='docx', size=len(source_bytes), purpose='general',
        file=ContentFile(source_bytes, name=name + '.docx'))
    own_sources.add(source.pk)
    assert Path(source.file.path).resolve().is_relative_to(media)
    response = client().post('/api/v1/files/' + str(source.pk) + '/office-preview/',
        {'lifecycle_version': 1}, format='json', HTTP_IDEMPOTENCY_KEY=prefix + '_' + name)
    assert response.status_code == 202, (name, response.status_code)
    job = OfficePreview.objects.get(pk=response.data['data']['id'])
    own_jobs.add(job.pk)
    own_records.add(job.record_id)
    TaskRecord.objects.filter(pk=job.record_id).update(created_at=timezone.now()-timedelta(days=400))
    claim = None
    if running or succeeded or lost:
        claim = office.claim()
        assert claim and claim['job_id'] == str(job.pk)
        assert claim['source'] == source_bytes
    if succeeded:
        office.finish(job.pk, claim['token'], output=pdf_bytes)
    if lost:
        OfficePreview.objects.filter(pk=job.pk).update(
            claimed_at=timezone.now()-timedelta(seconds=office.LEASE_SECONDS+1))
    job.refresh_from_db()
    return source, job, claim


def job_api(job, *, cancel=False, pdf=False):
    url = '/api/v1/files/office-preview/jobs/' + str(job.pk) + ('/pdf/' if pdf else '/')
    response = client().delete(url) if cancel else client().get(url)
    return response.status_code, response.data if hasattr(response, 'data') else bytes(response.content)


def history_preview(job):
    response = client(auditor_token).post('/api/v1/tasks/cleanup/',
        {'days': 1, 'batch_size': 1, 'dry_run': True}, format='json')
    assert response.status_code == 200, response.status_code
    data = response.data['data']
    assert data['ids'] == [str(job.record_id)], '清理预览必须只有本案例的专属记录'
    return {'days': 1, 'batch_size': 1, 'dry_run': False,
            'confirmation': '执行清理', 'preview_token': data['preview_token']}


def history_execute(values):
    response = client(auditor_token).post('/api/v1/tasks/cleanup/', values, format='json')
    assert response.status_code == 200, response.status_code
    assert response.data['data']['deleted'] == 1
    return response.status_code


def finish_refused(job, claim):
    try:
        office.finish(job.pk, claim['token'], output=pdf_bytes)
    except ValueError as error:
        assert str(error) == 'claim_not_running', type(error).__name__
        return 'refused'
    raise AssertionError('无效/已终结领取不应写入成功')


def thread_call(callback, observer=None):
    connections.close_all()
    current = connections['default']
    try:
        with current.cursor() as cursor:
            cursor.execute("SET lock_timeout = '6s'")
            cursor.execute("SET statement_timeout = '12s'")
            cursor.execute('SELECT current_database(), pg_backend_pid()')
            database, backend = cursor.fetchone()
            assert database == 'foundation'
        if observer:
            with current.execute_wrapper(observer):
                return backend, callback()
        return backend, callback()
    finally:
        current.close()


def locks(sql, model):
    return ('FOR UPDATE' in sql.upper() and 'SELECT' in sql.upper()
            and '"' + model._meta.db_table + '"' in sql)


def record_race(primary, secondary, *, after_wait=None):
    """A到record锁前暂停；B真实取得record锁后放行A，暴露旧job→record反向锁。"""
    ready, held = Event(), Event()
    seen_primary, seen_secondary = False, False

    def before(execute, sql, params, many, context):
        nonlocal seen_primary
        if not seen_primary and locks(sql, TaskRecord):
            seen_primary = True
            ready.set()
            assert held.wait(8), '第二连接未取得任务锁'
        return execute(sql, params, many, context)

    def after(execute, sql, params, many, context):
        nonlocal seen_secondary
        result = execute(sql, params, many, context)
        if not seen_secondary and locks(sql, TaskRecord):
            seen_secondary = True
            held.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(thread_call, primary, before)
        try:
            assert ready.wait(8), '主连接未到达任务锁'
            if after_wait:
                after_wait()
            second = pool.submit(thread_call, secondary, after)
            second_pid, second_result = second.result(timeout=16)
        finally:
            held.set()
        first_pid, first_result = first.result(timeout=16)
    assert first_pid != second_pid, '必须是不同 PostgreSQL 后端连接'
    assert seen_primary and seen_secondary
    return first_result, second_result


def probe_race(primary, intervene):
    """A已有Office probe但尚未锁actor；先让真实取消/历史/TTL完成。"""
    ready, release = Event(), Event()
    paused = False

    def observer(execute, sql, params, many, context):
        nonlocal paused
        if not paused and locks(sql, User):
            paused = True
            ready.set()
            assert release.wait(12), '未释放probe后的用户锁同步点'
        return execute(sql, params, many, context)

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(thread_call, primary, observer)
        try:
            assert ready.wait(8), '主连接未读取probe并进入身份锁'
            intervene()
        finally:
            release.set()
        _, result = first.result(timeout=16)
    assert paused
    return result


def assert_source(source):
    assert source.file.storage.exists(source.file.name)
    with source.file.open('rb') as content:
        assert hashlib.sha256(content.read()).hexdigest() == hashlib.sha256(source_bytes).hexdigest()


def discard(source, job):
    """只结束并移除本案例；所有执行/断言已经完成后调用。"""
    assert source.pk in own_sources and job.pk in own_jobs
    current = OfficePreview.objects.filter(pk=job.pk).first()
    if current and current.record_id:
        current.record.refresh_from_db()
        if current.record.status in ('pending', 'running'):
            assert job_api(current, cancel=True)[0] == 200
        TaskRecord.objects.filter(pk=current.record_id, creator=actor).delete()
    OfficePreview.objects.filter(pk=job.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
    local_only()
    office.cleanup()
    assert not OfficePreview.objects.filter(pk=job.pk).exists()
    assert_source(source)
    source.file.delete(save=False)
    FileModel.objects.filter(pk=source.pk, uploader=actor).delete()
    checks.append('passed')


successful = False
try:
    with override_settings(ROOT_URLCONF=url_name, ALLOWED_HOSTS=['localhost'],
            ADMINCORE_MODULES=('files', 'tasks', 'organization'), ADMINCORE_BUILD_PROFILE='full',
            ADMINCORE_OFFICE_PREVIEW_ENABLED=True,
            ADMINCORE_OFFICE_IMAGE='admincore/office-pg-fixture@sha256:' + 'a'*64,
            MEDIA_ROOT=str(media), STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
        assert office.available()
        # Simultaneous claimers must produce one lease, never duplicate work.
        source, job, _ = fixture('double_claim')
        go, entered = Event(), [Event(), Event()]
        def claiming(index):
            entered[index].set()
            assert go.wait(8)
            return office.claim()
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(thread_call, lambda index=index: claiming(index)) for index in (0, 1)]
            assert all(event.wait(8) for event in entered)
            go.set()
            results = [future.result(timeout=16) for future in pending]
        assert results[0][0] != results[1][0]
        assert sum(result is not None for _, result in results) == 1
        assert OfficePreview.objects.get(pk=job.pk).claim_digest
        discard(source, job)

        for operation in ('claim', 'finish'):
            source, job, lease = fixture('cancel_before_' + operation, running=operation == 'finish')
            callback = office.claim if operation == 'claim' else lambda: finish_refused(job, lease)
            result = probe_race(callback, lambda: job_api(job, cancel=True))
            assert (result is None) if operation == 'claim' else (result == 'refused')
            job.record.refresh_from_db()
            assert job.record.status == 'cancelled'
            assert not default_storage.exists('office-preview/' + str(job.pk) + '/preview.pdf')
            discard(source, job)

        # Record->preview lock order is shared by read, cancellation and completion.
        for operation in ('get', 'cancel', 'finish', 'claim'):
            source, job, lease = fixture('cleanup_vs_' + operation, lost=operation != 'claim')
            callback = (office.claim if operation == 'claim' else
                        (lambda: finish_refused(job, lease)) if operation == 'finish' else
                        (lambda: job_api(job, cancel=operation == 'cancel')))
            expire = (lambda: OfficePreview.objects.filter(pk=job.pk).update(
                expires_at=timezone.now()-timedelta(seconds=1))) if operation == 'claim' else None
            result, _ = record_race(callback, office.cleanup, after_wait=expire)
            if operation in ('get', 'cancel'):
                assert result[0] == 200 and result[1]['data']['status'] == 'failed'
            else:
                assert (result is None) if operation == 'claim' else (result == 'refused')
            job.record.refresh_from_db()
            assert job.record.status == 'failed' and job.record.error == 'runner_lost'
            assert not default_storage.exists('office-preview/' + str(job.pk) + '/preview.pdf')
            discard(source, job)

        # Real history endpoint deletes a successful TaskRecord while private PDF is read.
        source, job, _ = fixture('history_vs_pdf', succeeded=True)
        output_key = job.output_key
        values = history_preview(job)
        result, _ = record_race(lambda: job_api(job, pdf=True), lambda: history_execute(values))
        assert result[0] == 404
        job.refresh_from_db()
        assert job.record_id is None and default_storage.exists(output_key)
        assert_source(source)
        discard(source, job)
        assert not default_storage.exists(output_key)

        # Probe can disappear between initial read and actual actor/business locks.
        for operation in ('get', 'finish', 'claim'):
            source, job, lease = fixture('deleted_probe_' + operation, running=operation == 'finish')
            callback = (office.claim if operation == 'claim' else
                        (lambda: finish_refused(job, lease)) if operation == 'finish' else
                        (lambda: job_api(job)))
            def remove_probe():
                assert job_api(job, cancel=True)[0] == 200
                history_execute(history_preview(job))
                OfficePreview.objects.filter(pk=job.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
                office.cleanup()
                assert not OfficePreview.objects.filter(pk=job.pk).exists()
            result = probe_race(callback, remove_probe)
            if operation == 'get':
                assert result[0] == 404
            else:
                assert (result is None) if operation == 'claim' else (result == 'refused')
            assert not TaskRecord.objects.filter(pk=job.record_id).exists()
            assert not default_storage.exists('office-preview/' + str(job.pk) + '/preview.pdf')
            discard(source, job)

        local_only()
        assert not OfficePreview.objects.exists()
        assert not FileModel.objects.filter(pk__in=own_sources).exists()
        assert not TaskRecord.objects.filter(pk__in=own_records).exists()
        assert len(checks) == 11
        successful = True
        print('通过：Office PostgreSQL 11项真实双连接竞争；单次claim、取消不复活、失联清理、历史SET_NULL/TTL与probe删除受控；无死锁/超时；原件保持一致', flush=True)
finally:
    sys.modules.pop(url_name, None)
    connections.close_all()
    if successful:
        assert media.parent == Path(tempfile.gettempdir()).resolve()
        assert media.name.startswith('admincore-office-pg-' + suffix + '-')
        shutil.rmtree(media)
        print('已清理本脚本独立媒体目录；专属用户/审计留在一次性foundation供主代理核对', flush=True)
    else:
        print('保留失败Office PG夹具媒体目录：' + str(media), flush=True)
