"""公告能力登记不能自动扩大已有角色，也不能恢复管理员删除的菜单。"""
from io import StringIO

import pytest
from django.core.management import call_command

from apps.permissions.models import Menu, Permission, Role, RolePermission


pytestmark = pytest.mark.django_db


def test_announcement_upgrade_registers_without_granting_or_restoring_menu(admin_user, monkeypatch):
    admin_user.set_password('Existing-announcement-fixture#2026')
    admin_user.save()
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'unused-existing-user')
    role = Role.objects.create(name='系统管理员')
    call_command('bootstrap_admincore', stdout=StringIO())
    codes = ['announcement:read', 'announcement:update', 'announcement:publish']
    assert Permission.objects.filter(code__in=codes).count() == 3
    assert not RolePermission.objects.filter(role=role, permission__code__in=codes).exists()
    menu = Menu.objects.get(path='/notifications/announcements')
    assert menu.permission is None  # All authenticated readers can see published announcements.
    menu.delete()
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not Menu.objects.filter(path='/notifications/announcements').exists()


def test_disabled_notifications_hide_announcements_menu(admin_client):
    from django.test import override_settings

    Menu.objects.create(name='公告', path='/notifications/announcements')
    with override_settings(ADMINCORE_MODULES=()):
        assert admin_client.get('/api/v1/permissions/menus/my_menu/').json()['data'] == []
