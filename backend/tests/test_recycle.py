"""回收站的权限、状态转换、存储故障与通用模型接入契约。"""
import json
from datetime import timedelta

import pytest
from django.db import connection, models
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from apps.core.models import SoftDeleteModel, LifecycleConflict, Department, OrganizationMembership, DataScopeGrant
from apps.files.models import FileModel
from apps.logs.models import OperationLog
from apps.permissions.models import Role, Permission, RolePermission, UserRole
from apps.tasks.models import TaskRecord
from apps.tasks.tasks import cleanup_soft_deleted_files


def grant(user, *codes):
    role, _ = Role.objects.get_or_create(name='回收站测试角色')
    UserRole.objects.get_or_create(role=role, user=user)
    for code in codes:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={
            'name': code, 'resource': resource, 'action': action,
        })
        RolePermission.objects.get_or_create(role=role, permission=permission)
    return role


def file_for(user, name='private.txt', deleted=True):
    row = FileModel.objects.create(original_name=name, uploader=user, file_type='txt', size=7,
                                   file=SimpleUploadedFile(name, b'fixture'))
    if deleted:
        row.soft_delete(actor=user)
    return row


def items(*rows):
    return [{'id': str(row.pk), 'lifecycle_version': row.lifecycle_version} for row in rows]


def batch(client, action, *rows, **extra):
    return client.post('/api/v1/files/recycle_action/', {'action': action, 'items': items(*rows), **extra}, format='json')


@pytest.mark.django_db
def test_restore_preserves_bytes_owner_key_and_audit(admin_client, admin_user):
    row = file_for(admin_user)
    key = row.file.name
    before_logs = OperationLog.objects.count()
    listed = admin_client.get('/api/v1/files/recycle/').json()['data']['items']
    assert listed[0]['id'] == str(row.pk) and listed[0]['lifecycle_version'] == 2
    assert admin_client.get(f'/api/v1/files/{row.pk}/download/').status_code == 404
    response = admin_client.post(f'/api/v1/files/{row.pk}/restore/', {'lifecycle_version': 2}, format='json')
    assert response.status_code == 200
    row.refresh_from_db()
    assert not row.is_deleted and row.deleted_at is None and row.deleted_by_id is None
    assert row.lifecycle_version == 3 and row.file.name == key and row.uploader == admin_user
    assert b''.join(admin_client.get(f'/api/v1/files/{row.pk}/download/').streaming_content) == b'fixture'
    audit = OperationLog.objects.filter(resource_id=str(row.pk), action='update').get()
    values = json.loads(audit.description)
    assert values['before']['is_deleted'] and not values['after']['is_deleted']
    assert values['operation'] == 'restore' and OperationLog.objects.count() == before_logs + 2


@pytest.mark.django_db
def test_permissions_revocation_and_owner_scope(admin_client, member_client, admin_user, member_user):
    own, other = file_for(member_user), file_for(admin_user)
    assert member_client.get('/api/v1/files/recycle/').status_code == 403
    assert member_client.post(f'/api/v1/files/{own.pk}/restore/', {'lifecycle_version': 2}, format='json').status_code == 403
    role = grant(member_user, 'file:recycle', 'file:restore', 'file:purge')
    assert [row['id'] for row in member_client.get('/api/v1/files/recycle/').json()['data']['items']] == [str(own.pk)]
    result = batch(member_client, 'restore', own, other).json()["data"]
    assert [row['status'] for row in result['results']] == [200, 404]
    assert result['succeeded'] == result['failed'] == 1
    other.refresh_from_db()
    assert other.is_deleted
    result = batch(member_client, 'purge', other, dry_run=True).json()["data"]
    assert result['results'][0] == {'id': str(other.pk), 'status': 404, 'message': '文件不存在'}
    role.is_active = False
    role.save()
    assert batch(member_client, 'purge', other, confirmation='DELETE').status_code == 403


@pytest.mark.django_db
def test_department_scope_restore_does_not_change_owner(admin_client, member_client, admin_user, member_user):
    department = Department.objects.create(name='共享部门')
    OrganizationMembership.objects.create(user=admin_user, department=department)
    OrganizationMembership.objects.create(user=member_user, department=department)
    role = grant(member_user, 'file:recycle', 'file:restore')
    DataScopeGrant.objects.create(role=role, resource='file', scope='department')
    row = file_for(admin_user)
    assert batch(member_client, 'restore', row).json()['data']['succeeded'] == 1
    row.refresh_from_db()
    assert row.uploader_id == admin_user.pk
    DataScopeGrant.objects.filter(role=role).update(scope='self')
    assert member_client.get(f'/api/v1/files/{row.pk}/download/').status_code == 404


@pytest.mark.django_db
def test_versions_and_missing_storage_are_conflicts(admin_client, admin_user):
    row = file_for(admin_user)
    assert admin_client.post(f'/api/v1/files/{row.pk}/restore/', {}, format='json').status_code == 400
    assert admin_client.post(f'/api/v1/files/{row.pk}/restore/', {'lifecycle_version': 1}, format='json').status_code == 409
    row.file.storage.delete(row.file.name)
    assert batch(admin_client, 'restore', row).json()['data']['results'][0]['status'] == 409
    row.refresh_from_db()
    assert row.is_deleted and row.lifecycle_version == 2
    assert not OperationLog.objects.filter(resource_id=str(row.pk)).exists()
    assert json.loads(OperationLog.objects.get(action='other').description)['failed'] == 1


@pytest.mark.django_db
def test_delete_preview_confirmation_stale_snapshot_and_audit(admin_client, admin_user):
    row = file_for(admin_user)
    key = row.file.name
    preview = batch(admin_client, 'purge', row, dry_run=True).json()['data']
    assert preview['results'][0]['size'] == 7 and preview['succeeded'] == 1
    assert row.file.storage.exists(key) and OperationLog.objects.count() == 0
    assert batch(admin_client, 'purge', row).status_code == 400
    assert batch(admin_client, 'purge', row, confirmation='DELETE').json()['data']['succeeded'] == 1
    assert not FileModel.objects.filter(pk=row.pk).exists() and not row.file.storage.exists(key)
    log = OperationLog.objects.get(action='delete')
    assert log.resource_id == str(row.pk) and json.loads(log.description)['after'] is None
    another = file_for(admin_user)
    snapshot = items(another)
    another.restore(2)
    response = admin_client.post('/api/v1/files/recycle_action/', {
        'action': 'purge', 'items': snapshot, 'confirmation': 'DELETE',
    }, format='json')
    assert response.json()['data']['results'][0]['status'] == 409 and another.file.storage.exists(another.file.name)


@pytest.mark.django_db
def test_storage_failure_retains_row_and_rolls_back_audit(admin_client, admin_user, monkeypatch):
    row = file_for(admin_user)
    monkeypatch.setattr(row.file.storage, 'delete', lambda *_: (_ for _ in ()).throw(RuntimeError('SECRET fixture')))
    response = batch(admin_client, 'purge', row, confirmation='DELETE')
    assert response.json()['data']['results'][0]['status'] == 503
    assert 'SECRET' not in response.content.decode()
    assert FileModel.objects.filter(pk=row.pk, is_deleted=True).exists() and not OperationLog.objects.filter(action='delete').exists()
    assert json.loads(OperationLog.objects.get(action='other').description)['results'][0]['status'] == 503


@pytest.mark.django_db
def test_malformed_restore_id_is_not_server_error(admin_client):
    assert admin_client.post('/api/v1/files/not-a-uuid/restore/', {'lifecycle_version': 1}, format='json').status_code == 404


@pytest.mark.django_db
def test_policy_respects_disabled_schedule(admin_client):
    from django_celery_beat.models import PeriodicTask, IntervalSchedule
    schedule = IntervalSchedule.objects.create(every=1, period='days')
    entry = PeriodicTask.objects.create(name='fixture retention', task='tasks.cleanup_soft_deleted_files', interval=schedule, enabled=False)
    assert not admin_client.get('/api/v1/files/recycle_policy/').json()['data']['cleanup_enabled']
    entry.enabled = True
    entry.save()
    assert admin_client.get('/api/v1/files/recycle_policy/').json()['data']['cleanup_enabled']


@pytest.mark.django_db
def test_legacy_purge_rechecks_version_if_restore_wins(admin_client, admin_user, monkeypatch):
    row = file_for(admin_user)
    original = FileModel.hard_delete
    def restore_first(self, **kwargs):
        FileModel.objects.get(pk=self.pk).restore(2)
        return original(self, **kwargs)
    monkeypatch.setattr(FileModel, 'hard_delete', restore_first)
    assert admin_client.delete(f'/api/v1/files/{row.pk}/purge/').status_code == 409
    row.refresh_from_db()
    assert not row.is_deleted and row.file.storage.exists(row.file.name)


@pytest.mark.django_db
def test_upgrade_does_not_expand_existing_roles_or_recreate_removed_menu(monkeypatch):
    from django.core.management import call_command
    from apps.permissions.models import Menu
    monkeypatch.setenv('DJANGO_ENV', 'testing')
    editor = Role.objects.create(name='运营编辑')
    call_command('bootstrap_admincore', demo=True)
    assert not RolePermission.objects.filter(role=editor, permission__code__in=['file:recycle', 'file:restore', 'file:purge']).exists()
    assert Permission.objects.filter(code__in=['file:recycle', 'file:restore', 'file:purge']).count() == 3
    menu = Menu.objects.get(path='/files/recycle')
    assert menu.permission.code == 'file:recycle'
    menu.delete()
    call_command('bootstrap_admincore', demo=True)
    assert not Menu.objects.filter(path='/files/recycle').exists()


@pytest.mark.django_db
def test_batch_shape_limits_and_active_record_guard(admin_client, admin_user):
    row = file_for(admin_user, deleted=False)
    assert batch(admin_client, 'purge', row, dry_run=True).json()['data']['results'][0]['status'] == 409
    assert batch(admin_client, 'restore', row).json()['data']['results'][0]['status'] == 409
    assert batch(admin_client, 'restore', row, row).status_code == 400
    assert admin_client.post('/api/v1/files/recycle_action/', {'action': 'restore', 'items': []}, format='json').status_code == 400
    import uuid
    oversized = [{'id': str(uuid.uuid4()), 'lifecycle_version': 1} for _ in range(101)]
    assert admin_client.post('/api/v1/files/recycle_action/', {'action': 'purge', 'items': oversized, 'dry_run': True}, format='json').status_code == 400


@pytest.mark.django_db
def test_cleanup_preview_batches_rechecks_restored_snapshot(admin_user, monkeypatch):
    rows = [file_for(admin_user, f'expired-{index}.txt') for index in range(3)]
    FileModel.objects.filter(pk__in=[row.pk for row in rows]).update(deleted_at=timezone.now() - timedelta(days=40))
    preview = cleanup_soft_deleted_files(dry_run=True, batch_size=1)
    assert preview['eligible_files'] == 3 and preview['eligible_bytes'] == 21 and preview['purged_files'] == 0
    assert OperationLog.objects.count() == 0
    original = FileModel.hard_delete
    restored = []
    def intervene(self, **kwargs):
        if not restored:
            # 模拟扫描后、实际获取清理锁前发生恢复。
            self.restore(self.lifecycle_version)
            restored.append(self.pk)
        return original(self, **kwargs)
    monkeypatch.setattr(FileModel, 'hard_delete', intervene)
    assert cleanup_soft_deleted_files(batch_size=1)['purged_files'] == 2
    survivor = FileModel.objects.get(pk=restored[0])
    assert not survivor.is_deleted and survivor.file.storage.exists(survivor.file.name)
    assert OperationLog.objects.filter(action='delete').count() == 2
    assert TaskRecord.objects.filter(status='success').count() == 2


@pytest.mark.django_db
def test_cleanup_partial_failure_records_progress(admin_user, monkeypatch):
    rows = [file_for(admin_user, f'failure-{index}.txt') for index in range(2)]
    FileModel.objects.filter(pk__in=[row.pk for row in rows]).update(deleted_at=timezone.now() - timedelta(days=40))
    original = FileModel.hard_delete
    calls = []
    def fail_second(self, **kwargs):
        calls.append(self.pk)
        if len(calls) == 2:
            raise OSError('fixture storage unavailable')
        return original(self, **kwargs)
    monkeypatch.setattr(FileModel, 'hard_delete', fail_second)
    with pytest.raises(OSError):
        cleanup_soft_deleted_files(batch_size=1)
    assert TaskRecord.objects.get(status='failed').result['purged_files'] == 1
    assert FileModel.objects.count() == 1


@pytest.mark.django_db
@override_settings(ADMINCORE_MODULES=())
def test_closed_module_retains_trash_and_blocks_all_entries(admin_client, admin_user):
    row = file_for(admin_user)
    for path in ['recycle/', 'recycle_policy/']:
        assert admin_client.get('/api/v1/files/' + path).status_code == 404
    assert batch(admin_client, 'restore', row).status_code == 404
    assert admin_client.post(f'/api/v1/files/{row.pk}/restore/', {'lifecycle_version': 2}, format='json').status_code == 404
    assert FileModel.objects.filter(pk=row.pk, is_deleted=True).exists()


@pytest.mark.django_db
def test_recycle_search_pagination_and_policy(admin_client, admin_user):
    file_for(admin_user, 'matching.txt')
    file_for(admin_user, 'other.txt')
    response = admin_client.get('/api/v1/files/recycle/?search=matching&page_size=1').json()['data']
    assert response['pagination']['total'] == 1 and response['items'][0]['original_name'] == 'matching.txt'
    with override_settings(ADMINCORE_MODULES=('files',)):
        assert admin_client.get('/api/v1/files/recycle_policy/').json()['data'] == {'retention_days': 30, 'cleanup_enabled': False}


@pytest.fixture
def lifecycle_table(transactional_db):
    class Record(SoftDeleteModel):
        code = models.CharField(max_length=30)
        department = models.ForeignKey(Department, on_delete=models.PROTECT)

        class Meta:
            app_label = 'core'
            db_table = 'test_opt_in_lifecycle'
            constraints = [models.UniqueConstraint(fields=['code'], condition=models.Q(is_deleted=False), name='test_active_lifecycle_code')]

        def validate_restore(self):
            if not self.department.is_active:
                raise LifecycleConflict('关联部门已停用')

    with connection.schema_editor() as editor:
        editor.create_model(Record)
    yield Record
    with connection.schema_editor() as editor:
        editor.delete_model(Record)


def test_opt_in_model_unique_and_related_conflicts(lifecycle_table):
    Record = lifecycle_table
    department = Department.objects.create(name='接入示例')
    deleted = Record.objects.create(code='reused', department=department)
    deleted.soft_delete()
    current = Record.objects.create(code='reused', department=department)
    with pytest.raises(LifecycleConflict, match='唯一字段'):
        deleted.restore(2)
    deleted.refresh_from_db()
    assert deleted.is_deleted and deleted.lifecycle_version == 2
    current.soft_delete()
    department.is_active = False
    department.save()
    with pytest.raises(LifecycleConflict, match='关联部门'):
        deleted.restore(2)
    department.is_active = True
    department.save()
    deleted.restore(2)
    assert not deleted.is_deleted and deleted.lifecycle_version == 3
