"""短联系方式不露全值，Django 后台不能绕过管理界面的脱敏合同。"""
import pytest
from django.contrib import admin
from django.test import Client

from apps.core.sensitive import mask_email, mask_phone
from apps.users.models import UserProfile


@pytest.mark.parametrize('value,expected', [('', ''), ('13876543210', '138****3210'),
    ('+86 13876543210', '861****3210'), ('123', '****'), ('12345678', '****')])
def test_phone_mask_short_values_do_not_reveal_all_digits(value, expected):
    assert mask_phone(value) == expected


@pytest.mark.parametrize('value,expected', [('', ''), ('a@example.test', '***@example.test'),
    ('ab@example.test', 'a***@example.test'), ('invalid', '***')])
def test_email_mask_short_local_part(value, expected):
    assert mask_email(value) == expected


@pytest.mark.django_db
def test_django_admin_masks_contacts_and_excludes_raw_form_fields(admin_user, member_user):
    email, phone, legacy = 'private-contact@example.test', '13876543210', '13987654321'
    member_user.email, member_user.phone = email, phone
    member_user.verified_email = email
    member_user.save()
    profile = UserProfile.objects.create(user=member_user, phone=legacy)
    client = Client()
    client.force_login(admin_user)
    for path in ('/admin/auth_app/user/', f'/admin/auth_app/user/{member_user.pk}/change/',
                 f'/admin/users/userprofile/{profile.pk}/change/'):
        response = client.get(path)
        assert response.status_code == 200
        html = response.content.decode()
        assert all(value not in html for value in (email, phone, legacy))
    user_admin = admin.site._registry[type(member_user)]
    assert 'email' not in user_admin.search_fields and 'phone' not in user_admin.search_fields


@pytest.mark.django_db
def test_bootstrap_new_sensitive_permission_does_not_expand_existing_role(admin_user, monkeypatch):
    from django.core.management import call_command
    from apps.permissions.models import Role, RolePermission
    import io
    role = Role.objects.create(name='系统管理员', description='保留既有授权')
    # 旧角色可以是已人工减权的管理员角色；新权限不能自动补回。
    monkeypatch.setenv('ADMINCORE_ADMIN_PASSWORD', 'unused-existing-admin')
    admin_user.set_password('ExistingSecure#6412')
    admin_user.save()
    call_command('bootstrap_admincore', stdout=io.StringIO())
    assert not RolePermission.objects.filter(role=role, permission__code='user:sensitive_read').exists()
