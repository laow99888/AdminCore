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
        if user.is_service_account:
            raise ValidationError('机器身份不能用于交互登录', code='service_account')
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

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_service_account=False)

    @transaction.atomic
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method == 'POST':
            from apps.users.safety import lock_management_users
            # 先锁管理员，再进入 Admin 审计读取目标的路径。
            ids = [request.user.pk]
            if object_id:
                from uuid import UUID
                try:
                    ids.append(UUID(object_id))
                except ValueError:
                    pass
            lock_management_users(ids)
        return super().changeform_view(request, object_id, form_url, extra_context)

    @transaction.atomic
    def changelist_view(self, request, extra_context=None):
        if request.method == 'POST':
            from apps.users.safety import lock_management_users
            from uuid import UUID
            ids = [request.user.pk]
            for value in request.POST.getlist('_selected_action'):
                try:
                    ids.append(UUID(value))
                except ValueError:
                    pass
            lock_management_users(ids)
        return super().changelist_view(request, extra_context)

    @transaction.atomic
    def delete_view(self, request, object_id, extra_context=None):
        if request.method == 'POST':
            from apps.users.safety import lock_management_users
            from uuid import UUID
            ids = [request.user.pk]
            try:
                ids.append(UUID(object_id))
            except ValueError:
                pass  # 交由 Django Admin 的无效对象处理，不在锁查询中产生 500。
            lock_management_users(ids)
        return super().delete_view(request, object_id, extra_context)

    def delete_model(self, request, obj):
        from apps.users.safety import protect_management_access
        protect_management_access(request.user, [obj], deleting=True)
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from apps.users.safety import protect_management_access
        protect_management_access(request.user, list(queryset), deleting=True)
        return super().delete_queryset(request, queryset)

    @transaction.atomic
    def user_change_password(self, request, id, form_url=''):
        return super().user_change_password(request, id, form_url)
    readonly_fields = ('is_service_account', 'must_change_password', 'avatar_file', 'profile_version',
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
            if {'is_active', 'is_staff', 'is_superuser'} & set(form.changed_data):
                from apps.users.safety import protect_management_access
                protect_management_access(request.user, [current], values={
                    field: getattr(obj, field) for field in ('is_active', 'is_staff', 'is_superuser')})
            if {'email', 'first_name', 'last_name', 'phone', 'avatar'} & set(form.changed_data):
                obj.profile_version += 1
        super().save_model(request, obj, form, change)
