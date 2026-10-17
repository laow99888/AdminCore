"""确定性生成独立模块代码；所有插值均来自已验证标识符或转义字面量。"""
from dataclasses import asdict
from pathlib import Path
import ast
import json
import re
from .spec import Definition, GenerationError

TEMPLATES = Path(__file__).with_name('templates')


def script_json(value):
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def render(definition: Definition):
    if getattr(definition, 'schema_version', 1) == 2:
        from .render_v2 import render_v2
        return render_v2(definition)
    module, model = definition.module, definition.model
    fields = definition.fields
    names = tuple(field.name for field in fields)
    all_fields = ('id', *names, 'creator', 'creator_name', 'version', 'created_at', 'updated_at')
    model_lines, serializer_lines, constraints = [], [], [
        f"models.CheckConstraint(condition=models.Q(version__gte=1), name={module + '_version_valid'!r})"]
    for field in fields:
        if field.kind in ('string', 'text'):
            model_lines.append(f"    {field.name} = models.{'TextField' if field.kind == 'text' else 'CharField'}(max_length={field.max_length}, blank={not field.required!r}, default={field.default!r})")
            serializer_lines.append(f"    {field.name} = serializers.CharField(max_length={field.max_length}, required={field.required!r}, allow_blank={not field.required!r})")
            if field.required:
                constraints.append(f"models.CheckConstraint(condition=~models.Q({field.name}=''), name={module + '_' + field.name + '_nonempty'!r})")
        elif field.kind == 'integer':
            model_lines.append(f"    {field.name} = models.IntegerField(default={field.default!r})")
            serializer_lines.append(f"    {field.name} = serializers.IntegerField(required={field.required!r}, min_value={field.minimum}, max_value={field.maximum})")
            constraints.append(f"models.CheckConstraint(condition=models.Q({field.name}__gte={field.minimum}, {field.name}__lte={field.maximum}), name={module + '_' + field.name + '_bounds'!r})")
        else:
            model_lines.append(f"    {field.name} = models.BooleanField(default={field.default!r})")
            serializer_lines.append(f"    {field.name} = serializers.BooleanField(required={field.required!r})")
    table_config = '' if not definition.table else f"        db_table = {definition.table!r}\n        managed = False\n"
    context = {
        'MODULE': module, 'API_PREFIX': module.replace('_', '-'), 'MODEL': model, 'TITLE_REPR': repr(definition.title),
        'TITLE_JSON': script_json(definition.title), 'FIELDS_REPR': repr(names),
        'ALL_FIELDS': repr(all_fields), 'MODEL_FIELDS': '\n'.join(model_lines),
        'SERIALIZER_FIELDS': '\n'.join(serializer_lines),
        'CONSTRAINTS': ',\n            '.join(constraints), 'TABLE_CONFIG': table_config,
        'SEARCH_FIELDS': repr(tuple(field.name for field in fields if field.kind in ('string', 'text'))),
        'FRONTEND_FIELDS': script_json([asdict(field) for field in fields]),
        'DEFAULTS': script_json({field.name: field.default for field in fields}),
        'DEFAULTS_PY': repr({field.name: field.default for field in fields}),
        'REQUIRED_TEXT_FIELDS': repr(tuple(field.name for field in fields if field.required and field.kind in ('string', 'text'))),
        'INDEX_NAME': repr(module + '_owner_ts'),
        'UNMANAGED': repr(bool(definition.table)),
    }
    files = {}
    for filename in ['apps.py', 'models.py', 'manifest.py', 'serializers.py', 'services.py', 'views.py', 'urls.py']:
        files[f'backend/apps/{module}/{filename}'] = template(filename, context)
    files[f'backend/apps/{module}/__init__.py'] = ''
    files[f'backend/apps/{module}/migrations/__init__.py'] = ''
    files[f'frontend/src/views/{module}/RecordListView.vue'] = template('RecordListView.vue', context)
    files[f'backend/tests/test_generated_{module}.py'] = template('test_module.py', context)
    files[f'docs/generated/{module}.md'] = template('module.md', context)
    for path, code in files.items():
        if path.endswith('.py'):
            try:
                ast.parse(code, filename=path)
            except SyntaxError as error:
                raise GenerationError('生成的Python代码无效：' + path) from error
    return files


def template(name, context):
    value = (TEMPLATES / (name + '.tmpl')).read_text(encoding='utf-8')
    def substitute(match):
        if match[1] not in context:
            raise GenerationError('生成模板存在未替换字段：' + name)
        return context[match[1]]
    # 一次插值；用户字面量中出现模板标记也不再被二次解释。
    return re.sub(r'@@([A-Z_]+)@@', substitute, value)
