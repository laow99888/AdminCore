"""
认证应用管理后台
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import User
from apps.core.sensitive import mask_email, mask_phone
from apps.logs.admin_audit import AuditedAdminMixin


class MFAAdminAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        from .models import TOTPDevice
        if TOTPDevice.objects.filter(user=user).exclude(active_secret='').exists():
            raise ValidationError('已启用双因素认证，请使用系统登录入口', code='mfa_required')


admin.site.login_form = MFAAdminAuthenticationForm


class RequiredPasswordChangeForm(AdminPasswordChangeForm):
    @transaction.atomic
    def save(self, commit=True):
        self.user = User.objects.select_for_update().get(pk=self.user.pk)
        user = super().save(commit=False)
        user.must_change_password = True
        user.session_version += 1
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(AuditedAdminMixin, BaseUserAdmin):
    """用户管理后台"""
    audit_resource = 'user'
    change_password_form = RequiredPasswordChangeForm

    @transaction.atomic
    def user_change_password(self, request, id, form_url=''):
        return super().user_change_password(request, id, form_url)
    readonly_fields = ('must_change_password', 'avatar_file', 'profile_version',
                       'masked_email', 'masked_phone', 'contact_verified')
    fieldsets = tuple((title, {**options, 'fields': tuple(field for field in options['fields'] if field != 'email')})
                      for title, options in BaseUserAdmin.fieldsets) + (
        ('联系方式（原值请在系统用户管理中确认密码查看）', {'fields': ('masked_email', 'masked_phone', 'contact_verified')}),
        ('额外信息', {'fields': ('avatar', 'last_login_ip', 'login_count', 'must_change_password', 'avatar_file', 'profile_version')}),
    )
    list_display = ('username', 'masked_email', 'is_active', 'login_count', 'created_at')
    search_fields = ('username', 'first_name', 'last_name')
    list_filter = ('is_active', 'created_at')

    @admin.display(description='邮箱')
    def masked_email(self, obj):
        return mask_email(obj.email)

    @admin.display(description='手机号')
    def masked_phone(self, obj):
        return mask_phone(obj.phone)

    @admin.display(description='邮箱已验证', boolean=True)
    def contact_verified(self, obj):
        return obj.email_verified

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not change:
            obj.must_change_password = True
        else:
            current = User.objects.select_for_update().get(pk=obj.pk)
            # 未编辑字段沿用锁内状态，避免后台表单覆盖头像绑定或改密状态。
            for field in User._meta.concrete_fields:
                if field.name not in form.changed_data:
                    setattr(obj, field.attname, getattr(current, field.attname))
            if {'email', 'first_name', 'last_name', 'phone', 'avatar'} & set(form.changed_data):
                obj.profile_version += 1
        super().save_model(request, obj, form, change)
