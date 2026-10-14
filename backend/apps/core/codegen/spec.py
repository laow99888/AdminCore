"""只接受业务字段声明，不从输入执行Python/SQL/模板表达式。"""
from dataclasses import dataclass
import keyword
import re
from importlib import import_module
from apps.core.contracts import Module, MenuDeclaration, validate_registry
from apps.core.modules import MODULES, CORE_MODULES


class GenerationError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str
    required: bool
    default: object
    max_length: int = 120
    minimum: int = 0
    maximum: int = 1000000


@dataclass(frozen=True)
class Definition:
    module: str
    title: str
    model: str
    fields: tuple[Field, ...]
    table: str = ''


def text(value, label, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(char) < 32 for char in value):
        raise GenerationError(label + '必须是有界非空文本')
    return value.strip()


def integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise GenerationError(label + '不是允许范围内的整数')
    return value


def parse_definition(value):
    if not isinstance(value, dict) or set(value) - {'module', 'title', 'model', 'fields', 'table'}:
        raise GenerationError('定义只能包含登记字段')
    module = text(value.get('module'), '模块标识', 20)
    devices = {'con', 'prn', 'aux', 'nul', *(f'com{number}' for number in range(1, 10)), *(f'lpt{number}' for number in range(1, 10))}
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,19}', module) or keyword.iskeyword(module) or module in devices:
        raise GenerationError('模块标识必须为小写Python标识符')
    if module in CORE_MODULES:
        raise GenerationError('不能为核心模块生成业务代码')
    from apps.logs.audit import FIELDS as audit_resources
    if module in audit_resources and module not in {item.key for item in MODULES}:
        raise GenerationError('模块标识与已有审计资源冲突')
    model = text(value.get('model'), '模型名', 48)
    if not re.fullmatch(r'[A-Z][A-Za-z0-9]{0,47}', model) or keyword.iskeyword(model):
        raise GenerationError('模型名必须为PascalCase标识符')
    title = text(value.get('title'), '模块标题', 40)
    table = value.get('table', '')
    if not isinstance(table, str) or (table and not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', table)):
        raise GenerationError('已有表名必须为单个小写标识符')
    if table and any(table.startswith(prefix + '_') for prefix in ('auth', 'auth_app', 'core', 'users', 'permissions', 'logs', 'files', 'tasks', 'notifications', 'data_io', 'approvals', 'example', 'django', 'token_blacklist')):
        raise GenerationError('禁止为框架内部数据表生成业务CRUD')
    # 使用同一模块规则，拒绝覆盖既有模块、API/页面及资源。
    api_prefix = module.replace('_', '-')
    declaration = Module(module, title, api_prefix, 'apps.' + module + '.urls', ('/' + api_prefix,),
        default_enabled=False, permissions=((module, 'read', title, module + ':read'),),
        menus=(MenuDeclaration(title, '/' + api_prefix, 'clipboard-check', module + ':read'),),
        data_resources=((module, title),))
    existing = next((item for item in MODULES if item.key == module), None)
    registry = MODULES
    if existing:
        if module in {'files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization', 'realtime', 'example'}:
            raise GenerationError('不能为内置模块生成业务代码')
        # 已登记的生成模块允许再次预览；不能借相同名字覆盖其他人工模块。
        try:
            manifest = import_module('apps.' + module + '.manifest')
        except ImportError as error:
            raise GenerationError('同名模块缺少可核验的生成标记') from error
        if (getattr(manifest, 'GENERATED_BY', None) != 'AdminCore.codegen.v1'
                or existing.api_prefix != declaration.api_prefix or existing.paths != declaration.paths):
            raise GenerationError('同名模块不是兼容的生成模块')
        registry = tuple(item for item in MODULES if item.key != module)
    try:
        validate_registry((*registry, declaration))
    except Exception as error:
        raise GenerationError('模块定义与现有注册冲突') from error
    rows = value.get('fields')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise GenerationError('业务字段数量必须为1–20')
    fields = []
    reserved = {'id', 'pk', 'creator', 'creator_id', 'creator_name', 'version', 'created_at', 'updated_at',
        'objects', 'save', 'delete', 'clean', 'full_clean', 'validate', 'Meta', 'DoesNotExist'}
    from django.db.models import Model
    reserved.update(dir(Model))
    sensitive = ('password', 'passwd', 'secret', 'token', 'credential', 'private_key', 'cookie', 'session')
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'name', 'label', 'kind', 'required', 'default', 'max_length', 'minimum', 'maximum'}:
            raise GenerationError('字段包含未登记选项')
        name = text(row.get('name'), '字段名', 30)
        if (not re.fullmatch(r'[a-z][a-z0-9_]{0,29}', name) or '__' in name or keyword.iskeyword(name)
                or name in reserved or any(part in name for part in sensitive)
                or name in {field.name for field in fields}):
            raise GenerationError('字段名重复、保留或不适合生成业务CRUD')
        kind = row.get('kind')
        if kind not in ('string', 'text', 'integer', 'boolean'):
            raise GenerationError('仅支持有界文本、整数和布尔字段；关系/金额/文件需人工建模')
        if (kind in ('string', 'text') and set(row) & {'minimum', 'maximum'}
                or kind in ('integer', 'boolean') and 'max_length' in row
                or kind == 'boolean' and set(row) & {'minimum', 'maximum'}):
            raise GenerationError('字段选项与类型不一致')
        label = text(row.get('label'), '字段标签', 40)
        required = row.get('required', True)
        if type(required) is not bool:
            raise GenerationError('required必须是布尔值')
        length = integer(row.get('max_length', 2000 if kind == 'text' else 120), '文本上限', 1, 2000)
        low = integer(row.get('minimum', 0), '最小值', -2147483648, 2147483647)
        high = integer(row.get('maximum', 1000000), '最大值', low, 2147483647)
        default = row.get('default', '' if kind in ('string', 'text') else low if kind == 'integer' else False)
        if (kind in ('string', 'text') and (not isinstance(default, str) or len(default) > length or '\x00' in default)
                or kind == 'integer' and (type(default) is not int or not low <= default <= high)
                or kind == 'boolean' and type(default) is not bool):
            raise GenerationError('字段默认值与类型或界限不一致')
        fields.append(Field(name, label, kind, required, default, length, low, high))
    return Definition(module, title, model, tuple(fields), table)
