"""显式模块契约；保留所有 Django app 和迁移，只裁剪业务入口与执行。"""
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    api_prefix: str
    urls: str
    paths: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()


MODULES = (
    Module('files', '文件管理', 'files', 'apps.files.urls', ('/files',)),
    Module('tasks', '任务中心', 'tasks', 'apps.tasks.urls', ('/tasks',)),
    Module('notifications', '通知中心', 'notifications', 'apps.notifications.urls', ('/notifications',)),
    Module('data_io', '数据导入导出', 'data-io', 'apps.data_io.urls', (), ('files', 'tasks'), ('data_io.run_data_import',)),
    Module('approvals', '单级审批', 'approvals', 'apps.approvals.urls', ('/approvals',), ('notifications',)),
    Module('system', '系统管理', 'system', 'apps.core.system_urls', ('/system/config', '/system/dictionaries', '/system/information', '/system/monitor', '/system/cache')),
    Module('organization', '组织与数据权限', 'organization', 'apps.core.organization_urls', ('/organization',)),
)
PRESETS = {'minimal': (), 'standard': tuple(m.key for m in MODULES), 'demo': tuple(m.key for m in MODULES)}
CORE_MODULES = ('core', 'auth_app', 'users', 'permissions', 'logs')
MAINTENANCE_TASKS = {
    'tasks.run_maintenance': ('tasks',),
    'tasks.cleanup_soft_deleted_files': ('tasks', 'files'),
    'tasks.cleanup_expired_notifications': ('tasks', 'notifications'),
    'core.dispatch_outbox': (),
    'core.cleanup_expired_idempotency': (),
}


def resolve_modules(preset, explicit=None, production=False):
    if preset not in PRESETS:
        raise ImproperlyConfigured('ADMINCORE_PRESET 必须为 minimal、standard 或 demo')
    if production and preset == 'demo':
        raise ImproperlyConfigured('生产环境禁止 demo 预设')
    selected = PRESETS[preset] if explicit is None else tuple(part.strip() for part in explicit.split(',') if part.strip())
    known = {module.key for module in MODULES}
    if len(set(selected)) != len(selected) or set(selected) - known:
        raise ImproperlyConfigured('ADMINCORE_MODULES 存在重复或未知模块')
    for module in MODULES:
        if module.key in selected and not set(module.dependencies) <= set(selected):
            raise ImproperlyConfigured(f'模块 {module.key} 需要：{", ".join(module.dependencies)}')
    return tuple(module.key for module in MODULES if module.key in selected)


def module_enabled(key):
    return key in CORE_MODULES or key in settings.ADMINCORE_MODULES


def path_enabled(path):
    return all(module_enabled(module.key) for module in MODULES
               if any(path == base or path.startswith(base + '/') for base in module.paths))


def task_enabled(name):
    if name in MAINTENANCE_TASKS:
        return all(module_enabled(key) for key in MAINTENANCE_TASKS[name])
    for module in MODULES:
        if name in module.tasks:
            return module_enabled(module.key)
    return False


def require_task(name):
    if not task_enabled(name):
        from celery.exceptions import Ignore
        raise Ignore(f'任务模块已关闭：{name}')


def capabilities():
    return {
        'contract_version': 1,
        'preset': settings.ADMINCORE_PRESET,
        'modules': [{'key': m.key, 'title': m.title, 'enabled': module_enabled(m.key),
                     'dependencies': list(m.dependencies), 'paths': list(m.paths)} for m in MODULES],
    }
