"""仅在 foundation PostgreSQL 中运行；真实 JWT/API 导入和逐行保存点验收。"""
import io
from pathlib import Path
import shutil
import sys
import tempfile
import types
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import override_settings
from django.urls import include, path
from rest_framework.test import APIClient

from apps.core.models import Post
from apps.data_io.resources import get_resource
from apps.data_io.tasks import run_data_import
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.tasks.models import TaskRecord

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connection.vendor == 'postgresql', '必须使用 PostgreSQL'
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    assert cursor.fetchone()[0] == 'foundation', '连接的实际数据库必须为 foundation'

suffix = uuid4().hex[:12]
prefix = 'resource_import_' + suffix
url_name = 'admincore_resource_import_validation_' + suffix
assert url_name not in sys.modules
urls = types.ModuleType(url_name)
urls.urlpatterns = [path('api/v1/data-io/', include('apps.data_io.urls')),
                    path('api/v1/auth/', include('apps.auth_app.urls'))]
sys.modules[url_name] = urls
media = Path(tempfile.mkdtemp(prefix='admincore-resource-import-' + suffix + '-')).resolve()
completed = False
User = get_user_model()


def login(user, password):
    client = APIClient(HTTP_HOST='localhost')
    response = client.post('/api/v1/auth/login/', {'username': user.username, 'password': password}, format='json')
    assert response.status_code == 200, '隔离导入账户必须经真实登录获取 JWT'
    client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.json()['access'])
    return client


def submit(client, resource, text):
    upload = io.BytesIO(text.encode('utf-8'))
    upload.name = 'resource.csv'
    response = client.post('/api/v1/data-io/import/', {'resource': resource, 'file': upload}, format='multipart')
    assert response.status_code == 200, '导入源文件必须经真实上传入口提交'
    record = TaskRecord.objects.get(pk=response.json()['data']['id'])
    assert record.import_execution.session_id, '新提交必须绑定 JWT 设备会话'
    source = record.import_execution.batch.source
    assert Path(source.file.path).resolve().is_relative_to(media), '源文件必须位于本次独立媒体目录'
    return record


def execute(record):
    run_data_import(str(record.pk))
    record.refresh_from_db()
    return record


try:
    with override_settings(
            ROOT_URLCONF=url_name, MEDIA_ROOT=str(media), ADMINCORE_STORAGE_BACKEND='local',
            STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                      'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
            CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': url_name}},
            ADMINCORE_MODULES=tuple(dict.fromkeys((*settings.ADMINCORE_MODULES, 'files', 'tasks', 'data_io', 'organization')))):
        with transaction.atomic():
            password = uuid4().hex + uuid4().hex
            admin = User.objects.create_superuser(prefix + '_admin', password=password)
            manager = login(admin, password)
            print('通过：真实 PostgreSQL 专属媒体目录和 JWT 会话提交资源导入', flush=True)

            for resource, model, unique, first, last, text in (
                ('roles', Role, 'name', prefix + '_role_a', prefix + '_role_b',
                 'name,description\n{first},ok\n{first},duplicate\n,missing\n{last},ok\n'),
                ('posts', Post, 'code', prefix + '_post_a', prefix + '_post_b',
                 'code,name,description\n{first},First,ok\n{first},Duplicate,no\nBAD CODE,Invalid,no\n{last},Last,ok\n'),
            ):
                config = get_resource(resource)
                original = config['create_row']

                def real_unique_conflict(data, model=model, unique=unique, first=first, original=original, resource=resource):
                    # Simulate a uniqueness race after validation using a real PostgreSQL constraint.
                    if data[unique] == first and model.objects.filter(**{unique: first}).exists():
                        model.objects.create(**({unique: first, 'is_active': False}
                            if resource == 'roles' else {unique: first, 'name': 'conflict', 'is_active': False}))
                        raise AssertionError('PostgreSQL唯一约束必须拒绝重复行')
                    return original(data)

                record = submit(manager, resource, text.format(first=first, last=last))
                with patch.dict(config, create_row=real_unique_conflict):
                    execute(record)
                assert record.status == 'success'
                assert (record.result['created'], record.result['failed'], record.result['processed']) == (2, 2, 4)
                imported = model.objects.filter(**{unique + '__in': [first, last]})
                assert imported.count() == 2 and not imported.filter(is_active=True).exists()
                if resource == 'roles':
                    assert not RolePermission.objects.filter(role__in=imported).exists()
                    assert not UserRole.objects.filter(role__in=imported).exists()
                else:
                    assert not imported.filter(assignments__isnull=False).exists()
                receipts = record.import_execution.batch.receipts.order_by('row')
                assert list(receipts.values_list('row', 'created')) == [(2, True), (3, False), (4, False), (5, True)]
                audits = OperationLog.objects.filter(task_record_id=record.pk, description='import_row_created')
                assert audits.count() == 2
                assert set(audits.values_list('resource_id', flat=True)) == set(str(row.pk) for row in imported)
                assert audits.filter(resource='role' if resource == 'roles' else 'post', audit_version=1).count() == 2
                print('通过：真实 PostgreSQL ' + resource + ' 重复键保存点和无效行仅回滚本行，后续成功且默认停用/不分配/审计账本一致', flush=True)

            for resource, text in (
                ('roles', 'name,permission_ids\n' + prefix + '_unsafe_role,[]\n'),
                ('roles', 'name,is_active\n' + prefix + '_unsafe_active,true\n'),
                ('posts', 'code,name,version\n' + prefix + '_unsafe_post,Unsafe,999\n'),
                ('users', 'username,email,is_staff\n' + prefix + '_unsafe_user,user@example.invalid,true\n'),
            ):
                before = (Role.objects.count(), Post.objects.count(), User.objects.count())
                record = execute(submit(manager, resource, text))
                assert record.status == 'failed' and record.error == 'import_unknown_columns'
                assert not record.import_execution.batch.receipts.exists()
                assert not OperationLog.objects.filter(task_record_id=record.pk, description='import_row_created').exists()
                assert (Role.objects.count(), Post.objects.count(), User.objects.count()) == before
            print('通过：真实 PostgreSQL 特权和未知列整批拒绝，无成功行、分配或逐行审计', flush=True)

            password = uuid4().hex + uuid4().hex
            operator = User.objects.create_user(prefix + '_operator', password=password)
            role = Role.objects.create(name=prefix + '_operator_role')
            UserRole.objects.create(user=operator, role=role)
            for code in ('data_io:import', 'user:create', 'task:retry', 'role:update', 'post:update'):
                resource, action = code.split(':')
                permission, _ = Permission.objects.get_or_create(code=code,
                    defaults={'resource': resource, 'action': action, 'name': code})
                RolePermission.objects.create(role=role, permission=permission)
            client = login(operator, password)
            for resource in ('roles', 'posts'):
                upload = io.BytesIO(b'name,description\nforbidden,no\n')
                upload.name = 'forbidden.csv'
                assert client.post('/api/v1/data-io/import/', {'resource': resource, 'file': upload}, format='multipart').status_code == 403
            first = prefix + '_created_before_revoke'
            second = prefix + '_blocked_after_revoke'
            record = submit(client, 'users', 'username,email\n' + first + ',one@example.invalid\n'
                            + second + ',two@example.invalid\n')
            config = get_resource('users')
            original = config['create_row']

            def create_then_revoke(data):
                result = original(data)
                RolePermission.objects.filter(role=role, permission__code='user:create').delete()
                return result

            with patch.dict(config, create_row=create_then_revoke):
                execute(record)
            assert record.status == 'failed' and record.error == 'execution_not_authorized_committed_rows_preserved'
            assert User.objects.filter(username=first).exists() and not User.objects.filter(username=second).exists()
            assert list(record.import_execution.batch.receipts.values_list('row', 'created')) == [(2, True)]
            assert OperationLog.objects.filter(task_record_id=record.pk, resource='user', description='import_row_created').count() == 1
            assert client.post('/api/v1/data-io/import/' + str(record.pk) + '/').status_code == 403
            assert record.import_execution.batch.executions.count() == 1
            print('通过：真实 PostgreSQL 每行重新授权，撤权保留已提交行、停止后续行且不能接续；非管理员即使有权限码仍不能导入角色/岗位', flush=True)
            transaction.set_rollback(True)
    assert not User.objects.filter(username__startswith=prefix).exists()
    assert not Role.objects.filter(name__startswith=prefix).exists()
    assert not Post.objects.filter(code__startswith=prefix).exists()
    completed = True
    print('通过：本段资源导入数据库夹具整体回滚', flush=True)
finally:
    sys.modules.pop(url_name, None)
    if completed:
        assert media.parent == Path(tempfile.gettempdir()).resolve()
        assert media.name.startswith('admincore-resource-import-' + suffix + '-')
        shutil.rmtree(media)
        print('通过：仅清理本次专属资源导入媒体目录', flush=True)
    else:
        print('保留资源导入失败媒体证据：' + str(media), flush=True)
