"""代码内显式声明扩展能力；不扫描目录、不执行环境变量指定的插件。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Parameter:
    key: str
    label: str
    kind: str
    default: object
    minimum: int = 0
    maximum: int = 100
    setting: str = ''


@dataclass(frozen=True)
class MenuDeclaration:
    name: str
    path: str
    icon: str
    permission: str | None
    order: int = 100


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    api_prefix: str
    urls: str
    paths: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    default_enabled: bool = True
    permissions: tuple[tuple[str, str, str, str], ...] = ()
    menus: tuple[MenuDeclaration, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    data_resources: tuple[tuple[str, str], ...] = ()
    audit_fields: tuple[tuple[str, tuple[str, ...]], ...] = ()
    contract_version: int = 1
    conflicts: tuple[str, ...] = ()
    task_requires: tuple[tuple[str, tuple[str, ...]], ...] = ()


def validate_registry(modules):
    """启动即拒绝重复声明、跨模块菜单/参数及缺失依赖。"""
    import re
    from django.core.exceptions import ImproperlyConfigured
    from .version import MODULE_CONTRACT_VERSION
    if not 1 <= len(modules) <= 128:
        raise ImproperlyConfigured('模块登记数量必须为1至128')
    seen = {key: set() for key in ('key', 'api', 'path', 'permission', 'parameter', 'resource', 'audit', 'task')}
    from .permission_declarations import PERMISSIONS
    seen['permission'].update(row[3] for row in PERMISSIONS)
    from .task_declarations import CORE_TASKS
    seen['task'].update(CORE_TASKS)
    seen['resource'].update(('user', 'log'))
    seen['api'].update(('auth', 'users', 'permissions', 'logs', 'reliability', 'modules', 'brand',
                        'schema', 'docs', 'redoc', 'dashboard', 'health'))
    core_paths = ('/', '/login', '/recover-password', '/change-password', '/users', '/roles',
                  '/menus', '/logs', '/settings', '/403', '/500', '/unavailable')
    known = {module.key for module in modules}
    for module in modules:
        if (type(module.contract_version) is not int or module.contract_version != MODULE_CONTRACT_VERSION
                or type(module.default_enabled) is not bool):
            raise ImproperlyConfigured('模块契约版本或默认启用状态不受支持：' + module.key)
        if (len(set(module.dependencies)) != len(module.dependencies)
                or len(set(module.conflicts)) != len(module.conflicts)
                or not set(module.conflicts) <= known or module.key in module.conflicts):
            raise ImproperlyConfigured('模块依赖或冲突声明无效：' + module.key)
        declarations = {'key': [module.key], 'api': [module.api_prefix], 'path': module.paths,
                        'permission': [row[3] for row in module.permissions],
                        'parameter': [row.key for row in module.parameters],
                        'resource': [row[0] for row in module.data_resources],
                        'audit': [row[0] for row in module.audit_fields], 'task': module.tasks}
        for kind, values in declarations.items():
            if len(set(values)) != len(values) or set(values) & seen[kind]:
                raise ImproperlyConfigured('模块声明重复：' + kind)
            seen[kind].update(values)
        if (not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', module.key)
                or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', module.api_prefix)
                or not set(module.dependencies) <= known or module.key in module.dependencies):
            raise ImproperlyConfigured('模块标识或依赖无效')
        task_names = [name for name, _ in module.task_requires]
        if (len(set(task_names)) != len(task_names)
                or not set(task_names) <= set(module.tasks)
                or any(not set(required) <= known or module.key in required
                       or len(set(required)) != len(required) for _, required in module.task_requires)):
            raise ImproperlyConfigured('模块任务依赖声明无效')
        if any(not path.startswith('/') or path.endswith('/') for path in module.paths):
            raise ImproperlyConfigured('模块页面必须为无尾斜杠的绝对路径')
        if any(path == base or (base != '/' and path.startswith(base + '/'))
               for path in module.paths for base in core_paths):
            raise ImproperlyConfigured('模块页面不能覆盖核心入口')
        codes = {row[3] for row in module.permissions}
        if any(code != resource + ':' + action or not re.fullmatch(r'[a-z][a-z0-9_]{0,49}:[a-z][a-z0-9_]{0,49}', code)
               for resource, action, _, code in module.permissions):
            raise ImproperlyConfigured('权限码与资源动作不一致')
        if any(not any(menu.path == base or menu.path.startswith(base + '/') for base in module.paths)
               or (menu.permission is not None and menu.permission not in codes) for menu in module.menus):
            raise ImproperlyConfigured('模块菜单必须登记页面与权限')
        setting_defaults = {'files.retention_days': 'FILE_SOFT_DELETE_RETENTION_DAYS',
                            'notifications.retention_days': 'NOTIFICATION_RETENTION_DAYS'}
        if any(not row.key.startswith(module.key + '.') or row.kind not in ('string', 'integer')
               or (row.setting and row.setting != setting_defaults.get(row.key))
               or row.minimum > row.maximum
               or (row.kind == 'integer' and (type(row.default) is not int or not row.minimum <= row.default <= row.maximum))
               or (row.kind == 'string' and (not isinstance(row.default, str) or not row.minimum <= len(row.default) <= row.maximum))
               for row in module.parameters):
            raise ImproperlyConfigured('模块参数只能声明自身命名空间的有界业务值')
        if any(not re.fullmatch(r'[a-z][a-z0-9_]{0,19}', resource) for resource, _ in module.data_resources):
            raise ImproperlyConfigured('模块数据范围资源无效')
    # 防止闭环依赖；关闭再开启也不得依赖装载顺序。
    graph = {module.key: module.dependencies for module in modules}
    complete = {}
    def walk(key, active):
        if key in active:
            raise ImproperlyConfigured('模块依赖存在循环')
        if key in complete:
            return complete[key]
        required = set(graph[key])
        for dependency in graph[key]:
            required.update(walk(dependency, active | {key}))
        complete[key] = required
        return required
    for key in known:
        walk(key, set())
    for module in modules:
        required = complete[module.key] | {module.key}
        if any(set(other.conflicts) & required for other in modules if other.key in required):
            raise ImproperlyConfigured('模块依赖链包含互斥能力：' + module.key)


def scope_resources(modules):
    resources = [('user', '用户'), ('log', '日志')] + [row for module in modules for row in module.data_resources]
    # 保留v1原有资源排序，扩展资源仍按显式登记顺序追加。
    legacy_order = {'user': 0, 'file': 1, 'task': 2, 'log': 3}
    return sorted(resources, key=lambda row: legacy_order.get(row[0], 4))
