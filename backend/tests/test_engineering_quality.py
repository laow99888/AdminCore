"""管理闭环、密码策略、维护任务和输入边界回归。"""
from datetime import timedelta
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from apps.permissions.models import Role, UserRole, Permission, RolePermission, Menu
from apps.notifications.models import Notification
import pytest

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.mark.parametrize('password', ['1', '123456789', 'password', 'alice2026'])
def test_admin_create_rejects_weak_password(admin_client, password):
    response = admin_client.post('/api/v1/users/', {'username': 'alice', 'email': 'alice@example.com', 'password': password}, format='json')
    assert response.status_code == 400
    assert not User.objects.filter(username='alice').exists()


@pytest.mark.parametrize('password', ['1', '123456789', 'password', 'member2026'])
def test_admin_reset_rejects_weak_password(admin_client, member_user, password):
    previous = member_user.password
    response = admin_client.post(f'/api/v1/users/{member_user.pk}/reset_password/', {'password': password}, format='json')
    assert response.status_code == 400
    member_user.refresh_from_db()
    assert member_user.password == previous


def test_admin_role_assignment_and_omitted_roles_preserved(admin_client, member_user):
    role = Role.objects.create(name='测试角色')
    response = admin_client.patch(f'/api/v1/users/{member_user.pk}/', {'version': 1, 'role_ids': [str(role.pk)]}, format='json')
    assert response.status_code == 200
    assert UserRole.objects.filter(user=member_user, role=role).exists()
    assert admin_client.patch(f'/api/v1/users/{member_user.pk}/', {'version': 2, 'first_name': '保留'}, format='json').status_code == 200
    assert UserRole.objects.filter(user=member_user, role=role).exists()
    assert admin_client.patch(f'/api/v1/users/{member_user.pk}/', {'version': 3, 'role_ids': []}, format='json').status_code == 200
    assert not UserRole.objects.filter(user=member_user).exists()


def test_user_manager_cannot_grant_roles(member_client, member_user):
    permission = Permission.objects.create(name='用户编辑', code='user:update', resource='user', action='update')
    manager = Role.objects.create(name='用户管理员')
    RolePermission.objects.create(role=manager, permission=permission)
    UserRole.objects.create(user=member_user, role=manager)
    powerful = Role.objects.create(name='高权限角色')
    response = member_client.patch(f'/api/v1/users/{member_user.pk}/', {'role_ids': [str(powerful.pk)]}, format='json')
    assert response.status_code == 403
    assert not UserRole.objects.filter(user=member_user, role=powerful).exists()


def test_role_assignment_rejects_duplicates_and_disabled_additions(admin_client, member_user):
    role = Role.objects.create(name='停用角色', is_active=False)
    url = f'/api/v1/users/{member_user.pk}/'
    assert admin_client.patch(url, {'version': 1, 'role_ids': [str(role.pk)]}, format='json').status_code == 400
    UserRole.objects.create(user=member_user, role=role)
    assert admin_client.patch(url, {'version': 1, 'role_ids': [str(role.pk)]}, format='json').status_code == 200
    assert admin_client.patch(url, {'version': 2, 'role_ids': [str(role.pk), str(role.pk)]}, format='json').status_code == 400
    assert UserRole.objects.filter(user=member_user, role=role).count() == 1


@pytest.mark.parametrize('days', ['abc', None, -1, 0, 3651, 1.5])
def test_cleanup_invalid_days_are_400_without_deletion(admin_client, days):
    from apps.tasks.models import TaskRecord
    record = TaskRecord.objects.create(name='保留记录', status='success')
    response = admin_client.post('/api/v1/tasks/cleanup/', {'days': days}, format='json')
    assert response.status_code == 400
    assert TaskRecord.objects.filter(pk=record.pk).exists()


def test_menu_crud_cycle_hidden_and_parent_deletion(admin_client, member_client):
    base = '/api/v1/permissions/menus/'
    root_response = admin_client.post(base, {'name': '根菜单', 'path': '/test-root'}, format='json')
    assert root_response.status_code == 201
    root_id = root_response.json()['data']['id']
    child_response = admin_client.post(base, {'name': '隐藏菜单', 'path': '/test-child', 'parent': root_id, 'is_visible': False}, format='json')
    assert child_response.status_code == 201
    child_id = child_response.json()['data']['id']
    assert member_client.patch(base + child_id + '/', {'name': '越权'}, format='json').status_code == 403
    assert admin_client.patch(base + root_id + '/', {'version': 1, 'parent': child_id}, format='json').status_code == 400
    assert admin_client.delete(base + root_id + '/').status_code == 400
    assert admin_client.get(base).json()['data']['items'][0]['children'][0]['id'] == child_id
    assert admin_client.get(base + 'my_menu/').json()['data'][0]['children'] == []
    assert admin_client.delete(base + child_id + '/').status_code == 200
    assert admin_client.delete(base + root_id + '/').status_code == 200


@pytest.mark.parametrize('path', ['https://example.com', '//example.com', '/users?token=x', '/bad\\path'])
def test_menu_rejects_external_or_ambiguous_paths(admin_client, path):
    response = admin_client.post('/api/v1/permissions/menus/', {'name': '非法菜单', 'path': path}, format='json')
    assert response.status_code == 400


def test_maintenance_initialization_preserves_operator_changes():
    call_command('configure_maintenance', stdout=StringIO())
    assert PeriodicTask.objects.count() == 7
    task = PeriodicTask.objects.get(task='tasks.cleanup_soft_deleted_files')
    assert task.enabled and task.crontab.hour == '3' and task.crontab.minute == '0'
    task.enabled = False
    task.crontab = CrontabSchedule.objects.create(minute='30', hour='4', timezone='Asia/Shanghai')
    task.save()
    call_command('configure_maintenance', stdout=StringIO())
    task.refresh_from_db()
    assert not task.enabled and task.crontab.hour == '4'
    assert PeriodicTask.objects.count() == 7


def test_bootstrap_preserves_menu_and_role_edits(admin_user, monkeypatch):
    admin_user.set_password('FixtureSafe#3846')
    admin_user.save()
    monkeypatch.setenv('DJANGO_ENV', 'testing')
    call_command('bootstrap_admincore', stdout=StringIO())
    menu = Menu.objects.get(path='/users')
    menu.name = '我的用户菜单'
    menu.is_visible = False
    menu.save()
    role = Role.objects.get(name='系统管理员')
    RolePermission.objects.filter(role=role).delete()
    count = Notification.objects.count()
    call_command('bootstrap_admincore', stdout=StringIO())
    menu.refresh_from_db()
    assert menu.name == '我的用户菜单' and not menu.is_visible
    assert not RolePermission.objects.filter(role=role).exists()
    assert Notification.objects.count() == count
    Menu.objects.all().delete()
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not Menu.objects.exists()


def test_notification_retention_respects_read_status(settings, member_user):
    from apps.tasks.tasks import cleanup_expired_notifications
    settings.NOTIFICATION_RETENTION_DAYS = 90
    old_read = Notification.objects.create(recipient=member_user, title='过期已读', is_read=True)
    old_unread = Notification.objects.create(recipient=member_user, title='过期未读')
    recent = Notification.objects.create(recipient=member_user, title='最近已读', is_read=True)
    Notification.objects.filter(pk=old_read.pk).update(read_at=timezone.now() - timedelta(days=91))
    Notification.objects.filter(pk=old_unread.pk).update(created_at=timezone.now() - timedelta(days=91))
    Notification.objects.filter(pk=recent.pk).update(read_at=timezone.now())
    cleanup_expired_notifications()
    assert not Notification.objects.filter(pk=old_read.pk).exists()
    assert Notification.objects.filter(pk__in=[old_unread.pk, recent.pk]).count() == 2


def test_file_retention_only_purges_expired_deleted_files(settings, member_user, tmp_path):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.files.models import FileModel
    from apps.tasks.tasks import cleanup_soft_deleted_files
    settings.MEDIA_ROOT = tmp_path
    settings.FILE_SOFT_DELETE_RETENTION_DAYS = 30
    def make_file(name, deleted, age):
        return FileModel.objects.create(original_name=name, file=SimpleUploadedFile(name, b'fixture'),
                                        uploader=member_user, is_deleted=deleted,
                                        deleted_at=timezone.now() - timedelta(days=age))
    expired = make_file('expired.txt', True, 31)
    active = make_file('active.txt', False, 31)
    recent = make_file('recent.txt', True, 1)
    expired_path = expired.file.path
    cleanup_soft_deleted_files()
    from pathlib import Path
    assert not Path(expired_path).exists()
    assert not FileModel.objects.filter(pk=expired.pk).exists()
    assert FileModel.objects.filter(pk__in=[active.pk, recent.pk]).count() == 2
    assert Path(active.file.path).exists() and Path(recent.file.path).exists()
