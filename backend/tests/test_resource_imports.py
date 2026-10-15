"""资源导入必须与人工写入口共享授权、模块和逐行事务边界。"""
import io
from unittest.mock import patch

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.core.models import Post
from apps.data_io.resources import get_resource
from apps.data_io.tasks import run_data_import
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.tasks.models import TaskRecord

pytestmark = pytest.mark.django_db


def submit(client, resource, text):
    upload = io.BytesIO(text.encode('utf-8'))
    upload.name = 'resource.csv'
    return client.post('/api/v1/data-io/import/', {'resource': resource, 'file': upload}, format='multipart')


def execute(response):
    assert response.status_code == 200, response.content
    record = TaskRecord.objects.get(pk=response.json()['data']['id'])
    run_data_import(str(record.pk))
    record.refresh_from_db()
    return record


def grant(user, *codes):
    role = Role.objects.create(name='import-operator')
    UserRole.objects.create(user=user, role=role)
    for code in codes:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code,
            defaults={'resource': resource, 'action': action, 'name': code})
        RolePermission.objects.create(role=role, permission=permission)
    return role


@pytest.mark.parametrize('resource,headers', [
    ('roles', ['name', 'description']), ('posts', ['code', 'name', 'description']),
])
def test_resource_templates_have_only_create_fields(admin_client, resource, headers):
    response = admin_client.get('/api/v1/data-io/template/', {'resource': resource})
    assert response.status_code == 200
    assert list(load_workbook(io.BytesIO(response.content)).active.values)[0] == tuple(headers)


def test_roles_are_new_inactive_and_unassigned_with_row_audit(admin_client):
    record = execute(submit(admin_client, 'roles', 'name,description\nnew-role,hello\nnew-role,duplicate\n,missing\n'))
    assert record.status == 'success'
    assert (record.result['created'], record.result['failed']) == (1, 2)
    row = Role.objects.get(name='new-role')
    assert not row.is_active and not row.permissions.exists()
    assert not UserRole.objects.filter(role=row).exists()
    audit = OperationLog.objects.get(resource='role', resource_id=str(row.pk), description='import_row_created')
    assert audit.after_values['name'] == row.name
    assert record.import_execution.batch.receipts.count() == 3


def test_posts_are_new_inactive_and_duplicate_errors_do_not_abort_rows(admin_client):
    record = execute(submit(admin_client, 'posts',
        'code,name,description\nfirst_post,First,ok\nfirst_post,Duplicate,no\nBAD CODE,Invalid,no\nlast_post,Last,ok\n'))
    assert record.status == 'success'
    assert (record.result['created'], record.result['failed']) == (2, 2)
    assert not Post.objects.filter(is_active=True).exists()
    assert OperationLog.objects.filter(resource='post', description='import_row_created').count() == 2


@pytest.mark.parametrize('resource,text', [
    ('roles', 'name,permission_ids\nunsafe,[]\n'),
    ('roles', 'name,is_active\nunsafe,true\n'),
    ('posts', 'code,name,version\nunsafe,Unsafe,999\n'),
    ('users', 'username,email,is_staff\nunsafe,user@example.com,true\n'),
])
def test_unknown_or_privileged_columns_reject_whole_source(admin_client, resource, text):
    record = execute(submit(admin_client, resource, text))
    assert record.status == 'failed' and record.error == 'import_unknown_columns'
    assert record.import_execution.batch.receipts.count() == 0


@pytest.mark.parametrize('resource', ['roles', 'posts'])
def test_member_cannot_import_admin_resources_even_with_codes(member_user, member_client, resource):
    grant(member_user, 'data_io:import', 'role:update', 'post:update')
    assert submit(member_client, resource, 'name,description\nunsafe,no\n').status_code == 403
    assert member_client.get('/api/v1/data-io/template/', {'resource': resource}).status_code == 403
    assert not member_client.get('/api/v1/data-io/resources/').json()['data']['resources']


def test_user_import_requires_create_permission_too(member_user, member_client):
    role = grant(member_user, 'data_io:import')
    assert submit(member_client, 'users', 'username,email\nnewuser,user@example.com\n').status_code == 403
    code = Permission.objects.create(name='user:create', code='user:create', resource='user', action='create')
    RolePermission.objects.create(role=role, permission=code)
    record = execute(submit(member_client, 'users', 'username,email\nnewuser,user@example.com\n'))
    assert record.status == 'success' and record.result['created'] == 1


def test_deactivated_actor_after_submission_cannot_write_or_resume(admin_user, admin_client):
    response = submit(admin_client, 'roles', 'name\nqueued-role\n')
    admin_user.is_active = False
    admin_user.save(update_fields=['is_active'])
    record = execute(response)
    assert record.status == 'failed' and not Role.objects.filter(name='queued-role').exists()
    assert admin_client.post(f'/api/v1/data-io/import/{record.pk}/').status_code == 401


def test_permission_revoked_between_rows_stops_before_next_commit(member_user, member_client):
    role = grant(member_user, 'data_io:import', 'user:create')
    config = get_resource('users')
    create = config['create_row']

    def create_then_revoke(data):
        result = create(data)
        RolePermission.objects.filter(role=role, permission__code='user:create').delete()
        return result

    response = submit(member_client, 'users', 'username,email\nfirst,user1@example.com\nsecond,user2@example.com\n')
    with patch.dict(config, create_row=create_then_revoke):
        record = execute(response)
    from django.contrib.auth import get_user_model
    assert record.status == 'failed'
    assert get_user_model().objects.filter(username='first').exists()
    assert not get_user_model().objects.filter(username='second').exists()
    assert member_client.post(f'/api/v1/data-io/import/{record.pk}/').status_code == 403


def test_closed_organization_hides_and_blocks_post_import(admin_client, settings):
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'organization')
    assert 'posts' not in {row['resource'] for row in admin_client.get('/api/v1/data-io/resources/').json()['data']['resources']}
    assert submit(admin_client, 'posts', 'code,name\nnew_post,New\n').status_code == 403
    assert admin_client.get('/api/v1/data-io/export/?resource=posts').status_code == 404
