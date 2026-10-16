"""显式模块契约；保留所有 Django app 和迁移，只裁剪业务入口与执行。"""
from .contracts import Module, validate_registry, scope_resources
from apps.example.manifest import MODULE as EXAMPLE_MODULE
from .version import MODULE_CONTRACT_VERSION
from .task_declarations import CORE_TASKS
from apps.files.manifest import MODULE as FILES_MODULE
from apps.tasks.manifest import MODULE as TASKS_MODULE
from apps.notifications.manifest import MODULE as NOTIFICATIONS_MODULE
from apps.data_io.manifest import MODULE as DATA_IO_MODULE
from apps.approvals.manifest import MODULE as APPROVALS_MODULE
from apps.core.system_manifest import MODULE as SYSTEM_MODULE
from apps.core.organization_manifest import MODULE as ORGANIZATION_MODULE
from apps.core.realtime_manifest import MODULE as REALTIME_MODULE
from apps.api_credentials.manifest import MODULE as API_CREDENTIALS_MODULE
from apps.sso.manifest import MODULE as SSO_MODULE
from apps.feature_flags.manifest import MODULE as FEATURE_FLAGS_MODULE
from apps.ip_policy.manifest import MODULE as IP_POLICY_MODULE
from apps.online_forms.manifest import MODULE as ONLINE_FORMS_MODULE
from apps.reports.manifest import MODULE as REPORTS_MODULE

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


BUILTIN_MODULES = (
    FILES_MODULE,
    TASKS_MODULE,
    NOTIFICATIONS_MODULE,
    DATA_IO_MODULE,
    APPROVALS_MODULE,
    SYSTEM_MODULE,
    ORGANIZATION_MODULE,
    REALTIME_MODULE,
)
MODULES = BUILTIN_MODULES + (EXAMPLE_MODULE, API_CREDENTIALS_MODULE, SSO_MODULE, FEATURE_FLAGS_MODULE, IP_POLICY_MODULE, ONLINE_FORMS_MODULE, REPORTS_MODULE)
PRESETS = {'minimal': (), 'standard': tuple(m.key for m in MODULES if m.default_enabled),
           'demo': tuple(m.key for m in MODULES if m.default_enabled)}
CORE_MODULES = ('core', 'auth_app', 'users', 'permissions', 'logs')
MAINTENANCE_TASKS = dict(CORE_TASKS)
MAINTENANCE_TASKS.update({name: (module.key, *dict(module.task_requires).get(name, ()))
                          for module in MODULES for name in module.tasks})


def resolve_modules(preset, explicit=None, production=False):
    validate_registry(MODULES)
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
        if module.key in selected and set(module.conflicts) & set(selected):
            raise ImproperlyConfigured(f'模块 {module.key} 与已选模块互斥：{", ".join(sorted(set(module.conflicts) & set(selected)))}')
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
        'contract_version': MODULE_CONTRACT_VERSION,
        'preset': settings.ADMINCORE_PRESET,
        'modules': [{'key': m.key, 'title': m.title, 'enabled': module_enabled(m.key),
                     'contract_version': m.contract_version, 'default_enabled': m.default_enabled,
                     'conflicts': list(m.conflicts),
                     'dependencies': list(m.dependencies),
                     # v1 客户端要求每条权限路径逐项登记；父级仍控制其全部子路由。
                     'paths': list(dict.fromkeys((*m.paths, *(menu.path for menu in m.menus)))),
                     'page_permissions': {menu.path: menu.permission for menu in m.menus
                                          if menu.permission is not None}} for m in MODULES],
        'scope_resources': [{'key': key, 'title': title} for key, title in scope_resources(MODULES)],
    }
