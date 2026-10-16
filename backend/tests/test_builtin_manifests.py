"""声明搬迁兼容性：固定旧提交的公开种子/白名单，验证真实初始化结果。"""
import ast
from dataclasses import asdict, replace
import hashlib
from importlib import import_module
from io import StringIO
import json
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from apps.core.contracts import Parameter, validate_registry
from apps.core.modules import BUILTIN_MODULES, MODULES, capabilities, task_enabled


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def test_declaration_move_preserves_2dac5c5_seed_and_audit_contracts():
    from apps.core.permission_declarations import PERMISSIONS
    from apps.core.management.commands.bootstrap_admincore import MENUS
    from apps.core.system_config import CONFIG_DEFINITIONS
    from apps.core.modules import MAINTENANCE_TASKS
    from apps.logs.audit import FIELDS
    permissions = list(PERMISSIONS) + [row for module in BUILTIN_MODULES for row in module.permissions]
    # 本轮新增备份权限单独验证；固定旧版的 45 项种子继续做摘要检查。
    backup_permissions = [row for row in permissions if row[0] == 'backup']
    assert backup_permissions == [('backup', 'read', '查看备份状态', 'backup:read'),
                                  ('backup', 'restore', '恢复备份', 'backup:restore')]
    permissions = [row for row in permissions if row[0] != 'backup']
    assert len(permissions) == 45 and len({row[3] for row in permissions}) == 45
    assert digest(sorted(permissions)) == 'c822d5bcec2e070008818f9ef1e30f4f2433c7c8d1d4660ce68997448573080f'
    templates = next(menu for module in BUILTIN_MODULES for menu in module.menus if menu.path == '/notifications/templates')
    menus = MENUS + [(templates.name, templates.path, templates.icon, templates.order, None, templates.permission)]
    assert [row for row in menus if row[1] == '/tasks/backups'] == [
        ('备份与恢复', '/tasks/backups', 'database-backup', 17, None, 'backup:read')]
    menus = [row for row in menus if row[1] != '/tasks/backups']
    assert digest(sorted(menus)) == '074c7cf5b4c73f4aa4935e5384c00732a8527841cc6a8db903aa243970ea9c04'
    # Fixed projection from 2dac5c5, not an open-ended list of new resources to exclude.
    # New fields belong to their own feature tests; no original field may disappear or reorder.
    legacy_audit_fields = {
        'message_template': ('id', 'code', 'enabled', 'revision', 'variables', 'content_sha256'),
        'message_delivery': ('id', 'template_id', 'revision', 'channels', 'count', 'status', 'attempts'),
        'user': ('id', 'username', 'is_active', 'is_staff', 'is_superuser', 'must_change_password', 'session_version', 'profile_version', 'role_ids', 'group_ids', 'django_permission_ids'),
        'role': ('id', 'name', 'is_active', 'permission_ids'),
        'menu': ('id', 'name', 'path', 'icon', 'order', 'parent_id', 'permission_id', 'is_visible'),
        'permission': ('id', 'name', 'code', 'resource', 'action'),
        'user_role': ('id', 'user_id', 'role_id'),
        'user_profile': ('id', 'user_id', 'department', 'position'),
        'notification': ('id', 'recipient_id', 'notification_type', 'is_read', 'read_at', 'content_length', 'content_sha256'),
        'task': ('id', 'task_type', 'status', 'progress', 'creator_id', 'celery_task_id'),
        'department': ('id', 'name', 'parent', 'order', 'is_active', 'version'),
        'membership': ('id', 'user', 'department', 'version'),
        'data_scope': ('id', 'role', 'resource', 'scope', 'departments', 'version'),
        'post': ('id', 'code', 'name', 'order', 'is_active', 'version'),
        'user_post': ('id', 'user', 'post', 'version'),
        'system_config': ('value',),
        'dictionary': ('id', 'code', 'name', 'is_active', 'version', 'items_count'),
        'maintenance_schedule': ('task', 'enabled', 'cron', 'kwargs'),
        'maintenance_run': ('key', 'options', 'preview_id', 'status'),
        'approval': ('id', 'status', 'request_type', 'applicant_id', 'assignee_id', 'decided_by_id', 'decided_at'),
        'announcement': ('id', 'version', 'status', 'content_format', 'content_length', 'content_sha256'),
        'file': ('id', 'purpose', 'size', 'file_type', 'is_deleted', 'deleted_at', 'deleted_by', 'lifecycle_version'),
        'file_transform': ('id', 'lifecycle_version', 'source_sha256', 'width', 'height', 'format', 'quality', 'watermark_sha256', 'opacity', 'position', 'output_sha256', 'size'),
        'lifecycle': ('category', 'count', 'ids'),
    }
    assert set(legacy_audit_fields) <= set(FIELDS)
    for resource, fields in legacy_audit_fields.items():
        assert set(fields) <= set(FIELDS[resource])
    projected = {resource: tuple(field for field in FIELDS[resource] if field in fields)
                 for resource, fields in legacy_audit_fields.items()}
    assert digest(projected) == 'cbaca682f802aaa9330b0d9f1414a8036543e0836946d9b3fda3b85bca923089'
    parameters = [asdict(row) for key, row in CONFIG_DEFINITIONS.items() if not key.startswith('example.')]
    assert digest(sorted(parameters, key=lambda row: row['key'])) == '9c5839150a66142744affffeb8b49bc555cd0bf82b12b38f935697105f124243'
    assert digest(MAINTENANCE_TASKS) == 'edc6bcc36bfacea8a61d6ed8350e4dc430d41b54091367c277db8f1e31ceb612'
    assert capabilities()['scope_resources'][:4] == [
        {'key': 'user', 'title': '用户'}, {'key': 'file', 'title': '文件'},
        {'key': 'task', 'title': '任务'}, {'key': 'log', 'title': '日志'}]


def test_capabilities_preserve_v1_exact_page_permission_path_contract():
    for module in capabilities()['modules']:
        assert set(module['page_permissions']) <= set(module['paths'])
        assert len(module['paths']) == len(set(module['paths']))


@pytest.mark.parametrize('module', BUILTIN_MODULES, ids=lambda row: row.key)
def test_builtin_declarations_are_static_and_explicit(module):
    if module.key in ('system', 'organization', 'realtime'):
        manifest = import_module('apps.core.' + module.key + '_manifest')
    else:
        manifest = import_module('apps.' + module.key + '.manifest')
    assert manifest.MODULE is module
    tree = ast.parse(Path(manifest.__file__).read_text(encoding='utf-8'))
    assert all(isinstance(node, (ast.Expr, ast.ImportFrom, ast.Assign)) for node in tree.body)
    assert all(node.module == 'apps.core.contracts' for node in tree.body if isinstance(node, ast.ImportFrom))
    validate_registry(MODULES)


@pytest.mark.parametrize('changes', [
    {'tasks': ('core.dispatch_outbox',)},
    {'task_requires': (('unknown', ('files',)),)},
    {'task_requires': (('tasks.run_maintenance', ('missing',)),)},
    {'task_requires': (('tasks.run_maintenance', ('tasks',)),)},
    {'task_requires': (('tasks.run_maintenance', ('files', 'files')),)},
    {'parameters': (Parameter('tasks.secret', 'secret', 'string', '', setting='SECRET_KEY'),)},
])
def test_invalid_task_and_environment_default_declarations_rejected(changes):
    modified = tuple(replace(module, **changes) if module.key == 'tasks' else module for module in MODULES)
    with pytest.raises(ImproperlyConfigured):
        validate_registry(modified)


@pytest.mark.parametrize('enabled,files,notifications', [((), False, False), (('tasks',), False, False),
    (('tasks', 'files'), True, False), (('tasks', 'notifications'), False, True),
    (('tasks', 'files', 'notifications'), True, True)])
def test_task_specific_optional_dependencies_are_enforced(settings, enabled, files, notifications):
    settings.ADMINCORE_MODULES = enabled
    assert task_enabled('tasks.cleanup_soft_deleted_files') is files
    assert task_enabled('tasks.cleanup_expired_notifications') is notifications
    assert task_enabled('core.cleanup_expired_sessions')


@pytest.mark.django_db
def test_reinitialize_preserves_deleted_menus_customizations_roles_and_configuration(admin_user, settings):
    from apps.core.models import BootstrapState, SystemConfig
    from apps.permissions.models import Menu, RolePermission
    settings.ADMINCORE_MODULES = tuple(module.key for module in MODULES)
    admin_user.set_password('ManifestFixture#987654321')
    admin_user.save()
    call_command('bootstrap_admincore', stdout=StringIO())
    removed = set(Menu.objects.filter(path__in=['/files', '/tasks/schedules', '/system/config',
        '/notifications/templates', '/example']).values_list('path', flat=True))
    assert len(removed) == 5
    Menu.objects.filter(path__in=removed).delete()
    Menu.objects.filter(path='/organization').update(name='本项目组织', order=71, is_visible=False)
    SystemConfig.objects.create(key='files.retention_days', value=48)
    RolePermission.objects.order_by('id').first().delete()
    grants = list(RolePermission.objects.order_by('id').values_list('id', 'role_id', 'permission_id'))
    markers = set(BootstrapState.objects.values_list('key', flat=True))
    settings.ADMINCORE_MODULES = ()
    call_command('bootstrap_admincore', stdout=StringIO())
    settings.ADMINCORE_MODULES = tuple(module.key for module in MODULES)
    call_command('bootstrap_admincore', stdout=StringIO())
    assert not Menu.objects.filter(path__in=removed).exists()
    assert Menu.objects.filter(path='/organization', name='本项目组织', order=71, is_visible=False).exists()
    assert list(RolePermission.objects.order_by('id').values_list('id', 'role_id', 'permission_id')) == grants
    assert set(BootstrapState.objects.values_list('key', flat=True)) == markers
    assert SystemConfig.objects.get(key='files.retention_days').value == 48


@pytest.mark.django_db
def test_builtin_parameter_defaults_and_disabled_visibility_preserve_legacy_semantics(settings):
    from apps.core.models import SystemConfig
    from apps.core.system_config import config_value, visible_definitions
    settings.ADMINCORE_MODULES = ('system',)
    settings.FILE_SOFT_DELETE_RETENTION_DAYS = 73
    assert config_value('files.retention_days') == 73
    SystemConfig.objects.create(key='files.retention_days', value=42)
    assert config_value('files.retention_days') == 42
    assert 'files.retention_days' in visible_definitions()
    assert 'example.title_limit' not in visible_definitions()
    settings.ADMINCORE_MODULES = ()
    assert config_value('files.retention_days') == 73
