"""
初始化权限和管理员；演示仅通过独立演示项目安全入口创建。

幂等设计：已存在的数据自动跳过，可重复执行。
用法：python manage.py bootstrap_admincore
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
import os

User = get_user_model()

# 历史弱凭据仅用于识别并拒绝不安全的旧初始化账户。
ADMIN_PASSWORD = 'Admin#12345'
DEMO_PASSWORD = 'Demo#12345'

# 权限清单（resource, action, name, code）
from apps.core.permission_declarations import PERMISSIONS as BASE_PERMISSIONS
PERMISSIONS = list(BASE_PERMISSIONS)

# 角色与权限码
from apps.core.modules import BUILTIN_MODULES, MODULES, module_enabled
# 仅移动声明来源；保留内置权限原有升级策略。新扩展仍不自动给旧角色扩权。
MODULE_PERMISSION_CODES = {row[3] for module in MODULES if module not in BUILTIN_MODULES
                           for row in module.permissions}
PERMISSIONS += [row for module in MODULES for row in module.permissions]
ROLES = {
    '系统管理员': ('全部权限', [code for *_, code in PERMISSIONS]),
    '运营编辑': ('内容与用户管理', ['user:read', 'user:create', 'file:upload', 'file:download', 'file:recycle', 'file:restore', 'approval:read']),
    '只读访客': ('仅查看', ['user:read', 'role:read', 'approval:read', 'log:read']),
}

# 菜单树（与前端路由对应）
from apps.core.menu_declarations import MENUS as CORE_MENUS
# 保留旧初始化批次和排序，已消费的标记不会重新播种被管理员删除的菜单。
MENUS = sorted(list(CORE_MENUS) + [(menu.name, menu.path, menu.icon, menu.order, None, menu.permission)
    for module in BUILTIN_MODULES for menu in module.menus if menu.path != "/notifications/templates"],
    key=lambda row: row[3])


class Command(BaseCommand):
    help = '初始化 AdminCore 权限与管理员（幂等，可重复执行）'

    def add_arguments(self, parser):
        parser.add_argument('--demo', action='store_true', help='仅显式隔离的演示项目；不再创建固定凭据')

    def handle(self, *args, **options):
        from apps.notifications.models import Notification
        from apps.permissions.models import Menu, Permission, Role, RolePermission

        demo_mode = options['demo']
        from django.conf import settings
        demo_mode = demo_mode or settings.ADMINCORE_PRESET == 'demo'
        if demo_mode and os.getenv('DJANGO_ENV') == 'production':
            raise CommandError('生产环境禁止 --demo')
        if demo_mode:
            call_command('demo_admincore', stdout=self.stdout)
            return
        username = os.getenv('ADMINCORE_ADMIN_USERNAME', 'admin')
        password = os.getenv('ADMINCORE_ADMIN_PASSWORD', '')
        existing = User.objects.filter(username=username).first()
        if existing and (not existing.is_superuser or existing.check_password(ADMIN_PASSWORD)):
            raise CommandError('现有初始化账户权限或密码不安全，请先通过管理命令修正')
        if existing is None:
            if not password:
                raise CommandError('首次初始化必须设置 ADMINCORE_ADMIN_PASSWORD')
            try:
                validate_password(password, User(username=username))
            except ValidationError as exc:
                raise CommandError('初始化密码不符合密码策略') from exc
            if password in (ADMIN_PASSWORD, DEMO_PASSWORD):
                raise CommandError('生产初始化不能使用演示密码')
        self.stdout.write('开始初始化基础数据...')

        # 1. 超级管理员
        admin, created = User.objects.get_or_create(
            username=username,
            defaults={'email': os.getenv('ADMINCORE_ADMIN_EMAIL', 'admin@example.com'), 'is_staff': True, 'is_superuser': True},
        )
        admin_created = created
        if created:
            admin.set_password(password)
            admin.must_change_password = True
            admin.save()
            self.stdout.write(self.style.SUCCESS(f'  创建超级管理员：{username}'))
        else:
            self.stdout.write(f'  超级管理员已存在：{username}（跳过）')

        # 3. 权限
        permission_map = {}
        new_permission_codes = set()
        for resource, action, name, code in PERMISSIONS:
            perm, permission_created = Permission.objects.get_or_create(
                resource=resource, action=action,
                defaults={'name': name, 'code': code},
            )
            permission_map[code] = perm
            if permission_created:
                new_permission_codes.add(code)
        self.stdout.write(f'  权限就绪：{len(permission_map)} 项')

        # 4. 角色 + 角色权限
        role_map = {}
        for role_name, (desc, codes) in ROLES.items():
            role, role_created = Role.objects.get_or_create(name=role_name, defaults={'description': desc})
            role_map[role_name] = role
            for code in codes:
                # 回收站升级只登记权限，不自动扩大已有角色权限；新库沿用声明的默认角色。
                if role_created or (code in new_permission_codes and code not in MODULE_PERMISSION_CODES | {'file:process', 'task:retry', 'user:sensitive_read', 'file:recycle', 'file:restore', 'file:purge', 'schedule:read', 'schedule:update', 'schedule:run', 'diagnostics:read', 'monitor:read', 'post:read', 'post:update', 'cache:read', 'cache:clear', 'announcement:read', 'announcement:update', 'announcement:publish', 'session:read', 'session:revoke', 'template:read', 'template:update', 'template:send'}):
                    RolePermission.objects.get_or_create(role=role, permission=permission_map[code])
        self.stdout.write(f'  角色就绪：{len(role_map)} 个')

        # 5. 菜单
        from apps.core.models import BootstrapState
        with transaction.atomic():
            _, first_menu_init = BootstrapState.objects.get_or_create(key='default_menus_v1')
            # 已有数据库直接接纳现有菜单；新库只初始化一次，之后允许修改和删除。
            if first_menu_init and not Menu.objects.exists():
                for name, path, icon, order, parent, perm_code in MENUS:
                    Menu.objects.create(name=name, path=path, icon=icon, order=order,
                                        permission=permission_map.get(perm_code) if perm_code else None)
        self.stdout.write(f'  菜单就绪：{Menu.objects.count()} 项')

        # 历史标记属于兼容边界：数据来自 manifest，不能改用新标记复活被删除的菜单。
        menu_declarations = {row[1]: row for row in MENUS}
        for module in BUILTIN_MODULES:
            for menu in module.menus:
                menu_declarations[menu.path] = (menu.name, menu.path, menu.icon, menu.order, None, menu.permission)
        legacy_groups = (
            ('system_menus_v1', ('/system/config', '/system/dictionaries')),
            ('organization_menu_v1', ('/organization',)),
            ('reliability_menu_v1', ('/reliability/events',)),
            ('files_recycle_menu_v1', ('/files/recycle',)),
            ('maintenance_menu_v1', ('/tasks/schedules',)),
            ('diagnostics_menus_v1', ('/system/information', '/system/monitor')),
            ('post_menu_v1', ('/organization/posts',)),
            ('cache_management_menu_v1', ('/system/cache',)),
            ('announcements_menu_v1', ('/notifications/announcements',)),
            ('online_users_menu_v1', ('/system/online-users',)),
            ('message_templates_menu_v1', ('/notifications/templates',)),
            ('codegen_menu_v2', ('/system/codegen',)),
        )
        for key, paths in legacy_groups:
            with transaction.atomic():
                _, first = BootstrapState.objects.get_or_create(key=key)
                if first:
                    for path in paths:
                        name, _, icon, order, _, code = menu_declarations[path]
                        Menu.objects.get_or_create(path=path, defaults={'name': name, 'icon': icon,
                            'order': order, 'permission': permission_map[code] if code else None})

        for module in MODULES:
            if module in BUILTIN_MODULES or not module_enabled(module.key) or not module.menus:
                continue
            with transaction.atomic():
                _, first = BootstrapState.objects.get_or_create(key='module:' + module.key + ':menus:v1')
                if first:
                    for menu in module.menus:
                        Menu.objects.get_or_create(path=menu.path, defaults={'name': menu.name, 'icon': menu.icon,
                            'order': menu.order, 'permission': permission_map[menu.permission] if menu.permission else None})

        Notification.push(
            recipient_ids=([admin.id] if admin_created else []),
            title='欢迎使用 AdminCore',
            content='系统基础数据已初始化，请妥善保管账户凭据。',
            notification_type='system',
            link='/',
        )
        call_command('configure_maintenance', stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS('初始化完成 ✔'))
