"""只读识别已有 PostgreSQL 业务表；不执行输入 SQL，也不迁移表结构。"""
import re
from django.contrib.auth import get_user_model
from django.db import connection
from .spec import GenerationError, parse_definition


def inspect_table(table, module, model, title):
    # 复用名称/框架表拦截规则；业务字段稍后从元数据读取。
    base = {'module': module, 'model': model, 'title': title, 'table': table,
        'fields': [{'name': 'record_label', 'label': '名称', 'kind': 'string'}]}
    parse_definition(base)
    if connection.vendor != 'postgresql':
        raise GenerationError('已有表识别目前只支持PostgreSQL')
    with connection.cursor() as cursor:
        cursor.execute('''SELECT c.relkind, c.relrowsecurity, c.relispartition,
            EXISTS(SELECT 1 FROM pg_trigger t WHERE t.tgrelid=c.oid AND NOT t.tgisinternal)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND c.relname=%s''', [table])
        structure = cursor.fetchone()
        if structure != ('r', False, False, False):
            raise GenerationError('仅支持无自定义触发器/行安全策略的普通业务表')
        cursor.execute('''SELECT column_name, data_type, is_nullable, character_maximum_length
            FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s
            ORDER BY ordinal_position''', [table])
        columns = {name: (kind, nullable == 'YES', length) for name, kind, nullable, length in cursor.fetchall()}
        if not columns:
            raise GenerationError('指定业务表不存在')
        constraints = connection.introspection.get_constraints(cursor, table)
        cursor.execute('''SELECT EXISTS(SELECT 1 FROM pg_constraint
            WHERE confrelid = %s::regclass AND contype = 'f')''', [connection.ops.quote_name(table)])
        if cursor.fetchone()[0]:
            raise GenerationError('已有表被其他表引用，需要人工定义删除与关联保护')
        cursor.execute('''SELECT confdeltype FROM pg_constraint
            WHERE conrelid=%s::regclass AND contype='f' ''', [connection.ops.quote_name(table)])
        if any(row[0] not in ('a', 'r') for row in cursor.fetchall()):
            raise GenerationError('创建者外键必须拒绝级联删除或置空')
    structural = {'id': 'uuid', 'creator_id': 'uuid', 'version': 'integer',
        'created_at': 'timestamp with time zone', 'updated_at': 'timestamp with time zone'}
    if any(name not in columns or columns[name][0] != kind or columns[name][1] for name, kind in structural.items()):
        raise GenerationError('业务表必须包含非空UUID主键/创建者、整数版本和时区时间戳')
    primary = [row['columns'] for row in constraints.values() if row.get('primary_key')]
    if primary != [['id']]:
        raise GenerationError('业务表必须以id为唯一UUID主键')
    # 生成代码不会重建已有表；数据库本身必须拒绝非法版本。
    with connection.cursor() as cursor:
        quoted = connection.ops.quote_name(table)
        cursor.execute('SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = %s', [quoted, 'c'])
        checks = [re.sub(r'[\s()"]', '', row[0].lower()) for row in cursor.fetchall()]
    if not any('version>=1' in row or 'version>0' in row for row in checks):
        raise GenerationError('已有表必须包含version>=1数据库约束')
    user = get_user_model()._meta
    foreign = [(row['columns'], row['foreign_key']) for row in constraints.values() if row.get('foreign_key')]
    if len(foreign) != 1 or foreign[0] != (['creator_id'], (user.db_table, user.pk.column)):
        raise GenerationError('业务表仅支持creator_id关联当前用户；其他关系需人工建模')
    if any(row.get('unique') and row['columns'] != ['id'] for row in constraints.values()):
        raise GenerationError('业务表包含额外唯一约束，需要人工建模及冲突处理')
    fields = []
    supported_checks = {'checkversion>=0', 'checkversion>=1', 'checkversion>0'}
    for name, (kind, nullable, length) in columns.items():
        if name in structural:
            continue
        if nullable:
            raise GenerationError('业务字段暂不支持NULL，请人工定义空值语义')
        row = {'name': name, 'label': name, 'required': True}
        if kind == 'character varying' and length and length <= 2000:
            row.update(kind='string', max_length=length)
        elif kind == 'text':
            row.update(kind='text', max_length=2000)
        elif kind == 'integer':
            low, high = -2147483648, 2147483647
            for expression in checks:
                match = re.fullmatch(r'check' + re.escape(name) + r'>=(-?\d+)and' + re.escape(name) + r'<=(-?\d+)', expression)
                if match:
                    low, high = int(match[1]), int(match[2]); supported_checks.add(expression)
            row.update(kind='integer', minimum=low, maximum=high, default=max(low, min(0, high)))
        elif kind == 'boolean':
            row.update(kind='boolean', default=False)
        else:
            raise GenerationError('已有表包含不支持的字段类型：' + name)
        if row['kind'] in ('string', 'text'):
            supported_checks.add("checknot" + name + "::text=''::text")
            supported_checks.add("checknot" + name + "=''")
            row['required'] = any(expression in checks for expression in (
                "checknot" + name + "::text=''::text", "checknot" + name + "=''"))
        fields.append(row)
    if set(checks) - supported_checks:
        raise GenerationError('已有表包含不能自动解释的业务约束，请人工建模')
    result = {**base, 'fields': fields}
    parse_definition(result)
    return result


def verify_table(definition):
    inferred = parse_definition(inspect_table(definition.table, definition.module, definition.model, definition.title))
    expected = {row.name: row for row in inferred.fields}
    if set(expected) != {row.name for row in definition.fields}:
        raise GenerationError('定义与已有表的字段集合不一致')
    for row in definition.fields:
        actual = expected[row.name]
        if (row.kind != actual.kind or actual.required and not row.required
                or row.kind == 'string' and row.max_length > actual.max_length
                or row.kind == 'integer' and (row.minimum < actual.minimum or row.maximum > actual.maximum)):
            raise GenerationError('定义与已有表的字段类型或长度不一致：' + row.name)
