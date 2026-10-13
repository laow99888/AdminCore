"""
初始化权限和管理员；演示账号仅通过非生产环境的 --demo 创建。

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

# 固定凭据仅用于显式 --demo 的非生产环境。
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'Admin#12345'
DEMO_USERNAME = 'demo'
DEMO_PASSWORD = 'Demo#12345'

# 权限清单（resource, action, name, code）
PERMISSIONS = [
    ('user', 'read', '查看用户', 'user:read'),
    ('user', 'create', '创建用户', 'user:create'),
    ('user', 'update', '修改用户', 'user:update'),
    ('user', 'delete', '删除用户', 'user:delete'),
    ('role', 'read', '查看角色', 'role:read'),
    ('role', 'update', '修改角色', 'role:update'),
    ('file', 'upload', '上传文件', 'file:upload'),
    ('file', 'download', '下载文件', 'file:download'),
    ('file', 'recycle', '查看文件回收站', 'file:recycle'),
    ('file', 'restore', '恢复文件', 'file:restore'),
    ('file', 'purge', '彻底删除文件', 'file:purge'),
    ('approval', 'read', '查看审批', 'approval:read'),
    ('approval', 'decide', '审批处理', 'approval:decide'),
    ('log', 'read', '查看日志', 'log:read'),
    ('data_io', 'import', '数据导入', 'data_io:import'),
    ('data_io', 'export', '数据导出', 'data_io:export'),
    ('menu', 'read', '查看菜单配置', 'menu:read'),
    ('menu', 'update', '维护菜单配置', 'menu:update'),
    ('task', 'read', '查看任务', 'task:read'),
    ('task', 'cancel', '取消任务', 'task:cancel'),
    ('task', 'delete', '清理任务历史', 'task:delete'),
    ('config', 'read', '查看系统参数', 'config:read'),
    ('config', 'update', '修改系统参数', 'config:update'),
    ('dictionary', 'read', '查看数据字典', 'dictionary:read'),
    ('dictionary', 'update', '维护数据字典', 'dictionary:update'),
]

# 角色与权限码
ROLES = {
    '系统管理员': ('全部权限', [code for *_, code in PERMISSIONS]),
    '运营编辑': ('内容与用户管理', ['user:read', 'user:create', 'file:upload', 'file:download', 'file:recycle', 'file:restore', 'approval:read']),
    '只读访客': ('仅查看', ['user:read', 'role:read', 'approval:read', 'log:read']),
}

# 菜单树（与前端路由对应）
MENUS = [
    ('仪表盘', '/', 'layout-dashboard', 1, None, None),
    ('用户管理', '/users', 'users', 2, None, 'user:read'),
    ('角色权限', '/roles', 'shield-check', 3, None, 'role:read'),
    ('菜单管理', '/menus', 'list-tree', 4, None, 'menu:read'),
    ('文件管理', '/files', 'folder-open', 5, None, None),
    ('审批工作流', '/approvals', 'clipboard-check', 6, None, None),
    ('通知中心', '/notifications', 'bell', 7, None, None),
    ('任务中心', '/tasks', 'list-checks', 8, None, 'task:read'),
    ('操作日志', '/logs', 'file-text', 9, None, 'log:read'),
    ('系统设置', '/settings', 'settings', 10, None, None),
    ('系统参数', '/system/config', 'settings', 11, None, 'config:read'),
    ('数据字典', '/system/dictionaries', 'list-tree', 12, None, 'dictionary:read'),
    ('组织与数据权限', '/organization', 'users', 13, None, None),
    ('可靠事件', '/reliability/events', 'list-checks', 14, None, None),
    ('文件回收站', '/files/recycle', 'trash-2', 15, None, 'file:recycle'),
]


class Command(BaseCommand):
    help = '初始化 AdminCore 权限与管理员（幂等，可重复执行）'

    def add_arguments(self, parser):
        parser.add_argument('--demo', action='store_true', help='仅非生产环境：创建固定凭据的演示用户')

    def handle(self, *args, **options):
        from apps.notifications.models import Notification
        from apps.permissions.models import Menu, Permission, Role, RolePermission

        demo_mode = options['demo']
        from django.conf import settings
        demo_mode = demo_mode or settings.ADMINCORE_PRESET == 'demo'
        if demo_mode and os.getenv('DJANGO_ENV') == 'production':
            raise CommandError('生产环境禁止 --demo')
        username = ADMIN_USERNAME if demo_mode else os.getenv('ADMINCORE_ADMIN_USERNAME', 'admin')
        password = ADMIN_PASSWORD if demo_mode else os.getenv('ADMINCORE_ADMIN_PASSWORD', '')
        existing = User.objects.filter(username=username).first()
        if not demo_mode:
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
            admin.save()
            self.stdout.write(self.style.SUCCESS(f'  创建超级管理员：{username}'))
        else:
            self.stdout.write(f'  超级管理员已存在：{username}（跳过）')

        # 2. 演示用户
        demo = None
        demo_created = False
        if demo_mode:
            demo, created = User.objects.get_or_create(username=DEMO_USERNAME, defaults={'email': 'demo@example.com'})
            demo_created = created
            if created:
                demo.set_password(DEMO_PASSWORD)
                demo.save()
            self.stdout.write(f'  演示用户就绪：{DEMO_USERNAME}')

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
        from apps.permissions.models import UserRole
        role_map = {}
        for role_name, (desc, codes) in ROLES.items():
            role, role_created = Role.objects.get_or_create(name=role_name, defaults={'description': desc})
            role_map[role_name] = role
            for code in codes:
                # 回收站升级只登记权限，不自动扩大已有角色权限；新库沿用声明的默认角色。
                if role_created or (code in new_permission_codes and code not in {'file:recycle', 'file:restore', 'file:purge'}):
                    RolePermission.objects.get_or_create(role=role, permission=permission_map[code])
        if demo:
            UserRole.objects.get_or_create(user=demo, role=role_map['只读访客'])
        self.stdout.write(f'  角色就绪：{len(role_map)} 个（演示用户已绑定「只读访客」）')

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

        # 新模块菜单仅补录一次，之后保留管理员修改/删除。
        with transaction.atomic():
            _, first_system_init = BootstrapState.objects.get_or_create(key='system_menus_v1')
            if first_system_init:
                for name, path, icon, order, parent, perm_code in MENUS[10:12]:
                    Menu.objects.get_or_create(path=path, defaults={'name': name, 'icon': icon, 'order': order,
                                              'permission': permission_map[perm_code]})
        with transaction.atomic():
            _, first_org_init = BootstrapState.objects.get_or_create(key='organization_menu_v1')
            if first_org_init:
                Menu.objects.get_or_create(path='/organization', defaults={'name': '组织与数据权限', 'icon': 'users', 'order': 13})

        # 6. 欢迎通知
        with transaction.atomic():
            _, first_events_init = BootstrapState.objects.get_or_create(key='reliability_menu_v1')
            if first_events_init:
                Menu.objects.get_or_create(path='/reliability/events', defaults={'name': '可靠事件', 'icon': 'list-checks', 'order': 14})

        with transaction.atomic():
            _, first_recycle_init = BootstrapState.objects.get_or_create(key='files_recycle_menu_v1')
            if first_recycle_init:
                Menu.objects.get_or_create(path='/files/recycle', defaults={
                    'name': '文件回收站', 'icon': 'trash-2', 'order': 15,
                    'permission': permission_map['file:recycle'],
                })

        Notification.push(
            recipient_ids=([admin.id] if admin_created else []) + ([demo.id] if demo_created else []),
            title='欢迎使用 AdminCore',
            content='系统基础数据已初始化，请妥善保管账户凭据。',
            notification_type='system',
            link='/',
        )
        call_command('configure_maintenance', stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS('初始化完成 ✔'))
