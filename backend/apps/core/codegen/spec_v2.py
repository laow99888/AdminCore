"""V2 业务结构协议：仅接受数据，不接受表达式、代码或任意组件。"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import keyword
import re

from .spec import GenerationError, integer, parse_definition, text

KINDS = ('string', 'text', 'integer', 'boolean', 'decimal', 'date', 'datetime',
         'enum', 'dictionary', 'relation', 'file')
COMPONENTS = {'string': ('input', 'textarea'), 'text': ('textarea',), 'integer': ('number',),
              'boolean': ('switch', 'select'), 'decimal': ('decimal',), 'date': ('date',),
              'datetime': ('datetime',), 'enum': ('select', 'radio'), 'dictionary': ('select',),
              'relation': ('select',), 'file': ('select',)}


@dataclass(frozen=True)
class DefinitionV2:
    module: str
    title: str
    model: str
    fields: tuple
    structure: str
    details: tuple
    ordering: tuple
    approval: dict | None = None
    reports: dict | None = None
    schema_version: int = 2
    table: str = ''

    def as_dict(self):
        return {'schema_version': 2, 'module': self.module, 'title': self.title,
                'model': self.model, 'fields': list(self.fields), 'structure': self.structure,
                'details': list(self.details), 'ordering': list(self.ordering),
                **({'approval': self.approval} if self.approval else {}),
                **({'reports': self.reports} if self.reports else {})}


def identifier(value, label, model=False):
    from django.db.models import Model
    value = text(value, label, 48 if model else 30)
    pattern = r'[A-Z][A-Za-z0-9]{0,47}' if model else r'[a-z][a-z0-9_]{0,29}'
    reserved = {*dir(Model), 'id', 'pk', 'tenant', 'tenant_id', 'creator', 'creator_id',
                'creator_name', 'version', 'created_at', 'updated_at', 'parent', 'parent_id',
                'children', 'position', 'schema', 'schema_version', 'extensions',
                'approval_status', 'approval_request', 'approval_request_id',
                'page', 'page_size', 'ordering', 'format', 'search', 'display_labels', 'objects', 'all_objects'}
    if model:
        reserved.update({'Decimal', 'BaseModel', 'GeneratedService', 'GeneratedSerializerMixin', 'GeneratedListSerializer'})
    if (not re.fullmatch(pattern, value) or '__' in value or keyword.iskeyword(value)
            or value in reserved or (not model and any(part in value for part in
                ('password', 'passwd', 'secret', 'token', 'credential', 'private_key', 'cookie', 'session')))):
        raise GenerationError(label + '为保留名称或无效标识符')
    return value


def decimal_text(value, digits, places, label):
    if not isinstance(value, str) or not re.fullmatch(r'-?\d{1,18}(?:\.\d{1,8})?', value):
        raise GenerationError(label + '必须为定点十进制字符串')
    try:
        number = Decimal(value)
        if len(number.as_tuple().digits) > digits or -number.as_tuple().exponent > places or abs(number) >= Decimal(10) ** (digits - places):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise GenerationError(label + '超出金额精度') from None
    return value


def fields(rows, detail=False):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise GenerationError('每组业务字段数量必须为1–50')
    result, seen = [], set()
    common = {'name', 'label', 'kind', 'required', 'default', 'list', 'form', 'query', 'sortable', 'unique', 'indexed', 'component'}
    extras = {'string': {'max_length'}, 'text': {'max_length'}, 'integer': {'minimum', 'maximum'},
              'decimal': {'max_digits', 'decimal_places', 'minimum', 'maximum'}, 'enum': {'choices'},
              'dictionary': {'dictionary'}, 'relation': {'target'}}
    for raw in rows:
        if not isinstance(raw, dict) or not isinstance(raw.get('kind'), str) or raw['kind'] not in KINDS:
            raise GenerationError('不支持的业务字段类型')
        kind = raw['kind']
        if set(raw) - common - extras.get(kind, set()):
            raise GenerationError('字段选项未登记或不适用于当前类型')
        name = identifier(raw.get('name'), '字段名')
        if name in seen or any(name == item['name'] + '_id' and item['kind'] in {'relation', 'file'} or item['name'] == name + '_id' and kind in {'relation', 'file'} for item in result):
            raise GenerationError('字段名重复')
        seen.add(name)
        row = {'name': name, 'label': text(raw.get('label'), '字段标签', 40), 'kind': kind}
        for flag, default in [('required', True), ('list', True), ('form', True), ('sortable', False), ('unique', False), ('indexed', False)]:
            val = raw.get(flag, default)
            if type(val) is not bool:
                raise GenerationError(flag + '必须为布尔值')
            row[flag] = val
        if kind in {'text', 'file', 'relation'} and row['unique']:
            raise GenerationError('长文本和关联字段不支持生成唯一编码约束')
        query = raw.get('query', 'none')
        allowed = {'none', 'eq'} | ({'contains'} if kind in {'string', 'text'} else set()) | ({'range'} if kind in {'integer', 'decimal', 'date', 'datetime'} else set())
        if not isinstance(query, str) or query not in allowed or detail and query != 'none':
            raise GenerationError('查询方式与字段类型或明细配置不一致')
        row['query'] = query
        component = raw.get('component', COMPONENTS[kind][0])
        if not isinstance(component, str) or component not in COMPONENTS[kind]:
            raise GenerationError('控件类型不在字段控件白名单内')
        row['component'] = component
        if kind in {'string', 'text'}:
            row['max_length'] = integer(raw.get('max_length', 2000 if kind == 'text' else 120), '文本长度', 1, 10000)
        elif kind == 'integer':
            row['minimum'] = integer(raw.get('minimum', 0), '整数下限', -2147483648, 2147483647)
            row['maximum'] = integer(raw.get('maximum', 1000000), '整数上限', row['minimum'], 2147483647)
        elif kind == 'decimal':
            row['max_digits'] = integer(raw.get('max_digits', 18), '金额位数', 2, 18)
            row['decimal_places'] = integer(raw.get('decimal_places', 2), '小数位数', 0, min(8, row['max_digits'] - 1))
            for key in ('minimum', 'maximum'):
                if key in raw:
                    row[key] = decimal_text(raw[key], row['max_digits'], row['decimal_places'], key)
            if 'minimum' in row and 'maximum' in row and Decimal(row['minimum']) > Decimal(row['maximum']):
                raise GenerationError('金额上下界无效')
        elif kind == 'enum':
            choices = raw.get('choices')
            if not isinstance(choices, list) or not 1 <= len(choices) <= 100:
                raise GenerationError('枚举必须配置1–100项')
            normalized = []
            for item in choices:
                if not isinstance(item, dict) or set(item) != {'value', 'label'}:
                    raise GenerationError('枚举项必须只有 value 和 label')
                normalized.append({'value': text(item['value'], '枚举值', 80), 'label': text(item['label'], '枚举标签', 80)})
            if len({item['value'] for item in normalized}) != len(normalized):
                raise GenerationError('枚举值重复')
            row['choices'] = normalized
        elif kind == 'dictionary':
            row['dictionary'] = text(raw.get('dictionary'), '字典编码', 64)
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', row['dictionary']):
                raise GenerationError('字典编码无效')
        elif kind == 'relation':
            target = raw.get('target')
            if not isinstance(target, dict) or set(target) != {'module', 'model', 'label'}:
                raise GenerationError('关联必须明确 module、model、label')
            target_module = text(target['module'], '关联模块', 20)
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,19}', target_module):
                raise GenerationError('关联模块标识无效')
            from .spec import CORE_MODULES, MODULES
            if target_module in CORE_MODULES or any(item.key == target_module and item.key in {'files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization', 'realtime', 'example', 'api_credentials', 'sso', 'feature_flags', 'ip_policy', 'online_forms', 'reports'} for item in MODULES):
                raise GenerationError('不能为框架内部模型生成业务关联')
            row['target'] = {'module': target_module, 'model': identifier(target['model'], '关联模型', True), 'label': identifier(target['label'], '关联标签字段')}
        if 'default' in raw:
            val = raw['default']
        else:
            val = '' if kind in {'string', 'text', 'dictionary'} else row['minimum'] if kind == 'integer' else False if kind == 'boolean' else row.get('minimum', '0') if kind == 'decimal' else row['choices'][0]['value'] if kind == 'enum' else None
        if val is None:
            if kind not in {'date', 'datetime', 'relation', 'file'}:
                raise GenerationError('该类型的默认值不能为 null')
        elif kind in {'relation', 'file'}:
            raise GenerationError('关联与附件不允许固定默认记录')
        elif kind in {'string', 'text', 'dictionary'}:
            if not isinstance(val, str) or len(val) > row.get('max_length', 100) or '\x00' in val:
                raise GenerationError('文本默认值无效')
        elif kind == 'boolean' and type(val) is not bool:
            raise GenerationError('布尔默认值无效')
        elif kind == 'integer' and (type(val) is not int or not row['minimum'] <= val <= row['maximum']):
            raise GenerationError('整数默认值无效')
        elif kind == 'decimal':
            decimal_text(val, row['max_digits'], row['decimal_places'], '金额默认值')
            if ('minimum' in row and Decimal(val) < Decimal(row['minimum']) or 'maximum' in row and Decimal(val) > Decimal(row['maximum'])):
                raise GenerationError('金额默认值超出范围')
        elif kind == 'enum' and (not isinstance(val, str) or val not in {item['value'] for item in row['choices']}):
            raise GenerationError('枚举默认值无效')
        elif kind in {'date', 'datetime'}:
            try:
                parsed = date.fromisoformat(val) if kind == 'date' else datetime.fromisoformat(val)
                if kind == 'date' and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', val) or kind == 'datetime' and parsed.tzinfo is None:
                    raise ValueError()
            except (TypeError, ValueError):
                raise GenerationError('日期默认值无效，时间必须带时区') from None
        row['default'] = val
        result.append(row)
    return tuple(result)


def parse_definition_v2(raw):
    if set(raw) - {'schema_version', 'module', 'title', 'model', 'fields', 'structure', 'details', 'ordering', 'approval', 'reports'} or type(raw.get('schema_version')) is not int:
        raise GenerationError('V2定义只能包含登记字段，已有表仍使用V1核验协议')
    # 复用模块身份、路由、审计资源及已有生成模块冲突检查。
    identity = parse_definition({key: raw.get(key) for key in ('module', 'title', 'model')} | {'fields': [{'name': 'label', 'label': '名称', 'kind': 'string'}]})
    structure = raw.get('structure', 'single')
    if not isinstance(structure, str) or structure not in {'single', 'tree', 'master_detail'}:
        raise GenerationError('业务结构只能为 single、tree、master_detail')
    root_fields = fields(raw.get('fields'))
    detail_rows = raw.get('details', [])
    if not isinstance(detail_rows, list) or len(detail_rows) > 5 or (structure == 'master_detail') != bool(detail_rows):
        raise GenerationError('主子表必须配置1–5组明细，其他结构不允许明细')
    query_names = [row['name'] + suffix for row in root_fields if row['query'] != 'none'
                   for suffix in (['_min', '_max'] if row['query'] == 'range' else [''])]
    if len(query_names) != len(set(query_names)):
        raise GenerationError('生成的查询参数名重复')
    # 同时保护 FK 的隐式 attname 和 Django 忽略大小写的模型注册空间。
    seen_names = {name for row in root_fields for name in
                  ([row['name'], row['name'] + '_id'] if row['kind'] in {'relation', 'file'} else [row['name']])}
    identifier(identity.model, '模型名', True)
    seen_models, details = {identity.model.lower()}, []
    for raw_detail in detail_rows:
        if not isinstance(raw_detail, dict) or set(raw_detail) - {'name', 'label', 'model', 'fields', 'min_rows', 'max_rows'}:
            raise GenerationError('明细定义包含未登记字段')
        name = identifier(raw_detail.get('name'), '明细名')
        model = identifier(raw_detail.get('model'), '明细模型名', True)
        if name in seen_names or model.lower() in seen_models:
            raise GenerationError('明细名称或模型重复')
        seen_names.add(name); seen_models.add(model.lower())
        low = integer(raw_detail.get('min_rows', 0), '明细最少行数', 0, 200)
        details.append({'name': name, 'model': model, 'label': text(raw_detail.get('label'), '明细标签', 40),
                        'fields': list(fields(raw_detail.get('fields'), detail=True)), 'min_rows': low,
                        'max_rows': integer(raw_detail.get('max_rows', 100), '明细最多行数', max(1, low), 200)})
    groups = [(identity.model, root_fields), *[(item['model'], item['fields']) for item in details]]
    symbols = [name for name, _ in groups] + [name + 'Serializer' for name, _ in groups]
    symbols += [identity.model + 'VersionSerializer', identity.model + 'ListSerializer']
    symbols += [name + field['name'].title().replace('_', '') + 'Choice' for name, rows in groups for field in rows if field['kind'] == 'enum']
    if len(symbols) != len(set(symbols)):
        raise GenerationError('模型名称与生成的序列化类型冲突')
    ordering = raw.get('ordering', ['-created_at', '-id'])
    orderable = {row['name'] for row in root_fields if row['sortable']} | {'id', 'created_at', 'updated_at'}
    if (not isinstance(ordering, list) or not 1 <= len(ordering) <= 5 or any(not isinstance(item, str) or item.removeprefix('-') not in orderable for item in ordering)
            or len({item.removeprefix('-') for item in ordering}) != len(ordering)):
        raise GenerationError('默认排序必须引用已声明的排序字段且不能重复')
    approval = raw.get('approval')
    if 'approval' in raw:
        if (not isinstance(approval, dict) or set(approval) != {'flow_code', 'title_field'}
                or not isinstance(approval['flow_code'], str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,79}', approval['flow_code'])
                or not isinstance(approval['title_field'], str)
                or approval['title_field'] not in {f['name'] for f in root_fields if f['kind'] == 'string'}):
            raise GenerationError('审批配置必须指定流程编码和文本标题字段')
    reports = raw.get('reports')
    if 'reports' in raw:
        if not isinstance(reports, dict) or set(reports) != {'dimensions', 'metrics', 'filters'}:
            raise GenerationError('报表必须显式登记维度、指标和筛选字段')
        allowed = {
            'dimensions': {f['name'] for f in root_fields if f['kind'] in {'string', 'enum', 'dictionary', 'boolean', 'date', 'datetime'}} | {'created_at'},
            'metrics': {f['name'] for f in root_fields if f['kind'] in {'integer', 'decimal'}},
            'filters': {f['name'] for f in root_fields if f['kind'] in {'string', 'enum', 'dictionary', 'boolean', 'date', 'datetime', 'integer', 'decimal'}} | {'created_at'},
        }
        if approval:
            allowed['dimensions'].add('approval_status'); allowed['filters'].add('approval_status')
        for key, permitted in allowed.items():
            values = reports[key]
            if (not isinstance(values, list) or len(values) > 20 or any(not isinstance(value, str) for value in values)
                    or len(values) != len(set(values)) or not set(values) <= permitted):
                raise GenerationError('报表字段未登记或类型不支持')
    return DefinitionV2(identity.module, identity.title, identity.model, root_fields, structure, tuple(details), tuple(ordering), approval, reports)
