"""生成可审查的显式模型/序列化器；公共写入协议集中在 runtime。"""
import ast
import hashlib
from .render import template, script_json


def constraint_name(module, model, field, suffix):
    value = f'{module}_{model}_{field}_{suffix}'
    return 'cg_' + hashlib.sha256(value.encode()).hexdigest()[:24]


def model_field(field):
    kind, required = field['kind'], field['required']
    default = field['default']
    if kind in {'relation', 'file'}:
        target = 'files.FileModel' if kind == 'file' else field['target']['module'] + '.' + field['target']['model']
        return f'models.ForeignKey({target!r}, on_delete=models.PROTECT, related_name="+", null={not required!r}, blank={not required!r})'
    if kind in {'date', 'datetime'}:
        typ = 'DateTimeField' if kind == 'datetime' else 'DateField'
        return f'models.{typ}(null={not required!r}, blank={not required!r}' + (f', default={default!r}' if default is not None else '') + ')'
    if kind == 'decimal':
        return f"models.DecimalField(max_digits={field['max_digits']}, decimal_places={field['decimal_places']}, default={default!r})"
    if kind == 'integer':
        return f'models.IntegerField(default={default!r})'
    if kind == 'boolean':
        return f'models.BooleanField(default={default!r})'
    typ = 'TextField' if kind == 'text' else 'CharField'
    options = f"max_length={field.get('max_length', 100 if kind == 'dictionary' else 80)}, blank={not required!r}, default={default!r}"
    if kind == 'enum':
        options += ', choices=' + repr([(item['value'], item['label']) for item in field['choices']])
    return f'models.{typ}({options})'


def serializer_field(field):
    kind, required = field['kind'], field['required']
    args = f'required={required!r}'
    if not field['form']:
        args = 'read_only=True'
    if kind in {'relation', 'file'}:
        return f'serializers.UUIDField({args}, allow_null={not required!r}, source={field["name"] + "_id"!r})'
    if kind in {'date', 'datetime'}:
        return f'serializers.{"DateTimeField" if kind == "datetime" else "DateField"}({args}, allow_null={not required!r})'
    if kind == 'decimal':
        args += f", max_digits={field['max_digits']}, decimal_places={field['decimal_places']}, coerce_to_string=True"
        for key in ('minimum', 'maximum'):
            if key in field:
                args += f", {'min_value' if key == 'minimum' else 'max_value'}=Decimal({field[key]!r})"
        return f'serializers.DecimalField({args})'
    if kind == 'integer':
        return f"serializers.IntegerField({args}, min_value={field['minimum']}, max_value={field['maximum']})"
    if kind == 'boolean':
        return f'serializers.BooleanField({args})'
    if kind == 'enum':
        return f"serializers.ChoiceField({args}, choices={[(item['value'], item['label']) for item in field['choices']]!r})"
    return f"serializers.CharField({args}, max_length={field.get('max_length', 100 if kind == 'dictionary' else 80)}, allow_blank={not required!r})"


def model_class(definition, name, fields, parent=False):
    lines = [f'class {name}(BaseModel):']
    lines += [f"    {field['name']} = {model_field(field)}" for field in fields]
    if parent:
        lines += [f"    parent = models.ForeignKey({definition.model!r}, on_delete=models.CASCADE, related_name={parent!r})",
                  '    position = models.PositiveIntegerField(default=0)']
    else:
        lines += ["    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='" + definition.module + "_records')",
                  '    version = models.PositiveIntegerField(default=1)']
        if definition.approval:
            lines += ["    approval_status = models.CharField(max_length=16, default='draft', choices=[('draft', '草稿'), ('pending', '审批中'), ('approved', '已通过'), ('rejected', '已驳回'), ('cancelled', '已撤回')], db_index=True)",
                      "    approval_request = models.ForeignKey('approvals.ApprovalRequest', on_delete=models.PROTECT, null=True, blank=True, related_name='+')"]
        if definition.structure == 'tree':
            lines += ["    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children')"]
    constraints = []
    for field in fields:
        key = field['name']
        checks = []
        if field['kind'] == 'integer' or field['kind'] == 'decimal':
            for edge, op in [('minimum', 'gte'), ('maximum', 'lte')]:
                if edge in field:
                    value = f'Decimal({field[edge]!r})' if field['kind'] == 'decimal' else repr(field[edge])
                    checks.append(f'models.Q({key}__{op}={value})')
        if field['kind'] in {'string', 'text', 'dictionary'} and field['required']:
            checks.append(f'~models.Q({key}="")')
        if field['kind'] == 'enum':
            checks.append(f'models.Q({key}__in={tuple(item["value"] for item in field["choices"])!r})')
        if checks:
            constraints.append(f'models.CheckConstraint(condition={" & ".join(checks)}, name={constraint_name(definition.module, name, key, "valid")!r})')
        if field['unique']:
            if parent:
                constraints.append(f'models.UniqueConstraint(fields=["parent", {key!r}], name={constraint_name(definition.module, name, key, "unique")!r})')
            else:
                constraints += [f'models.UniqueConstraint(fields=["tenant", {key!r}], name={constraint_name(definition.module, name, key, "tenant_unique")!r})',
                                f'models.UniqueConstraint(fields=[{key!r}], condition=models.Q(tenant__isnull=True), name={constraint_name(definition.module, name, key, "global_unique")!r})']
    if not parent:
        constraints.append(f'models.CheckConstraint(condition=models.Q(version__gte=1), name={constraint_name(definition.module, name, "version", "valid")!r})')
        if definition.approval:
            constraints.append(f'models.CheckConstraint(condition=models.Q(approval_status__in=["draft", "pending", "approved", "rejected", "cancelled"]), name={constraint_name(definition.module, name, "approval", "valid")!r})')
    indexes = [f'models.Index(fields={(["parent", "position"] if parent else ["creator", "-created_at"])!r}, name={constraint_name(definition.module, name, "owner", "index")!r})']
    indexes += [f'models.Index(fields=[{field["name"]!r}], name={constraint_name(definition.module, name, field["name"], "index")!r})' for field in fields if field['indexed']]
    lines += ['', '    class Meta:', f'        ordering = {(["position", "id"] if parent else list(definition.ordering))!r}',
              f'        indexes = [{", ".join(indexes)}]', f'        constraints = [{", ".join(constraints)}]', '']
    return '\n'.join(lines)


def render_v2(definition):
    module, model = definition.module, definition.model
    schema = definition.as_dict()
    root = f'backend/apps/{module}/'
    files = {root + '__init__.py': '', root + 'migrations/__init__.py': '',
             root + 'schema.py': '# 此文件由生成器管理；业务扩展放在 extensions.py。\nSCHEMA = ' + repr(schema) + '\n'}
    files[root + 'models.py'] = ('from decimal import Decimal\nfrom django.conf import settings\nfrom django.db import models\nfrom apps.core.models import BaseModel\n\n\n'
        + model_class(definition, model, definition.fields) + '\n\n' + '\n\n'.join(model_class(definition, detail['model'], detail['fields'], detail['name']) for detail in definition.details))
    serializers = ['from decimal import Decimal', 'from rest_framework import serializers', 'from drf_spectacular.utils import extend_schema_serializer, extend_schema_field',
                   'from apps.core.codegen.runtime import GeneratedSerializerMixin, GeneratedListSerializer', 'from .schema import SCHEMA',
                   'from .models import ' + ', '.join([model] + [detail['model'] for detail in definition.details]), '', '']
    groups = [(detail['model'], detail['fields'], detail) for detail in definition.details] + [(model, definition.fields, None)]
    for class_name, fields, detail in groups:
        for field in fields:
            if field['kind'] == 'enum':
                enum_name = class_name + field['name'].title().replace('_', '') + 'Choice'
                serializers += [f"@extend_schema_field({{'type': 'string', 'enum': {[item['value'] for item in field['choices']]!r}}}, component_name='{module}_{class_name}_{field['name']}Choices')",
                                f'class {enum_name}(serializers.ChoiceField):', '    pass', '', '']
        serializers += [f"@extend_schema_serializer(component_name='{module}_{class_name}')", f'class {class_name}Serializer(GeneratedSerializerMixin, serializers.ModelSerializer):',
                        f'    field_spec = {list(fields)!r}', f'    detail_spec = {list(definition.details) if detail is None else []!r}', f'    is_detail = {detail is not None!r}']
        serializers += [f"    {field['name']} = " + serializer_field(field).replace('serializers.ChoiceField(', class_name + field['name'].title().replace('_', '') + 'Choice(') for field in fields]
        serializers += ['    display_labels = serializers.SerializerMethodField()']
        names = ['id', *[field['name'] for field in fields], 'display_labels']
        if detail is None:
            serializers += ['    version = serializers.IntegerField(min_value=0, required=True)', "    creator_name = serializers.CharField(source='creator.username', read_only=True)"]
            names += ['version', 'creator', 'creator_name', 'created_at', 'updated_at']
            if definition.approval:
                serializers += ['    approval_status = serializers.CharField(read_only=True)', '    approval_request = serializers.UUIDField(source="approval_request_id", read_only=True, allow_null=True)']
                names += ['approval_status', 'approval_request']
            if definition.structure == 'tree':
                serializers += ["    parent = serializers.UUIDField(source='parent_id', required=False, allow_null=True)"]
                names += ['parent']
            for item in definition.details:
                serializers += [f"    {item['name']} = {item['model']}Serializer(many=True, required=True, min_length={item['min_rows']}, max_length={item['max_rows']})"]
                names.append(item['name'])
        serializers += ['', '    class Meta:', f'        model = {class_name}', f'        fields = {tuple(names)!r}',
                        f'        read_only_fields = {(("id",) if detail else ("id", "creator", "created_at", "updated_at"))!r}',
                        '        list_serializer_class = GeneratedListSerializer', '', '']
    serializers += [f"@extend_schema_serializer(component_name='{module}_{model}Version')", f'class {model}VersionSerializer(serializers.Serializer):', '    version = serializers.IntegerField(min_value=1)', '']
    serializers += [f"@extend_schema_serializer(component_name='{module}_{model}List')", f'class {model}ListSerializer({model}Serializer):',
                    f'    class Meta({model}Serializer.Meta):', f'        fields = {tuple(["id", *[field["name"] for field in definition.fields], "display_labels", "version", "creator", "creator_name", "created_at", "updated_at"] + (["parent"] if definition.structure == "tree" else []) + (["approval_status", "approval_request"] if definition.approval else []))!r}', '']
    files[root + 'serializers.py'] = '\n'.join(serializers)
    files[root + 'services.py'] = f'''from apps.core.codegen.runtime import GeneratedService
from apps.logs.audit import write_audit
from .models import {model}
from .schema import SCHEMA
from . import extensions

service = GeneratedService({model}, SCHEMA, extensions, lambda **values: write_audit(**values))
visible = service.visible
locked_actor = service.locked_actor
mutate = service.mutate
'''
    files[root + 'extensions.py'] = '''"""手写扩展：生成器只在首次创建本文件。所有钩子处于写事务内。
校验可抛 DRF ValidationError；after_save 不发送邮件/HTTP，外部副作用请登记 outbox。
"""


def before_save(*, actor, instance, values, details):
    """可修改 values/details，例如服务端计算订单金额。instance 为 None 表示新增。"""
    pass


def after_save(*, actor, instance, action):
    """同一事务中的关联写入；抛异常会回滚业务、明细和审计。"""
    pass


def before_delete(*, actor, instance):
    """校验业务状态是否允许删除。"""
    pass
'''
    context = {'MODULE': module, 'MODEL': model, 'API_PREFIX': module.replace('_', '-'), 'TITLE_REPR': repr(definition.title),
               'TITLE_JSON': script_json(definition.title), 'SEARCH_FIELDS': repr(tuple(field['name'] for field in definition.fields if field['query'] == 'contains'))}
    for name in ['apps.py', 'urls.py', 'manifest.py', 'views.py', 'module.md']:
        value = template(name, context)
        if name == 'manifest.py':
            value = value.replace('AdminCore.codegen.v1', 'AdminCore.codegen.v2')
            if definition.approval:
                value = value.replace('    default_enabled=False,', "    dependencies=('approvals',),\n    default_enabled=False,")
                value = value.replace("('read', 'create', 'update', 'delete')", "('read', 'create', 'update', 'delete', 'submit', 'withdraw')")
        if name == 'views.py':
            value = value.replace('from drf_spectacular.utils import extend_schema, extend_schema_view', 'from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter')
            parameters = []
            for field in definition.fields:
                if field['query'] != 'none':
                    for suffix in (['_min', '_max'] if field['query'] == 'range' else ['']):
                        parameters.append(f'OpenApiParameter({field["name"] + suffix!r}, str, description={field["label"]!r})')
            if definition.structure == 'tree':
                parameters.append("OpenApiParameter('parent', str, description='父节点UUID；root表示根节点')")
            value = value.replace('@extend_schema_view(', '@extend_schema_view(\n    list=extend_schema(parameters=[' + ', '.join(parameters) + ']),', 1)
            value = value.replace('from rest_framework import viewsets', 'from rest_framework import viewsets\nfrom apps.core.codegen.runtime import GeneratedViewMixin\nfrom .services import service\nfrom .schema import SCHEMA')
            value = value.replace('class RecordViewSet(QueryBudgetListMixin,', 'class RecordViewSet(GeneratedViewMixin, QueryBudgetListMixin,')
            value = value.replace('    serializer_class = RecordSerializer', '    generated_schema = SCHEMA\n    generated_service = service\n    serializer_class = RecordSerializer')
            value = value.replace('from .serializers import ', f'from .serializers import {model}ListSerializer as ListSerializer\nfrom .serializers import ', 1)
            value = value.replace('    def get_queryset(self):\n        return visible(self.request.user)',
                '    def get_serializer_class(self):\n        return ListSerializer if self.action == "list" else RecordSerializer\n\n    def get_queryset(self):\n        rows = visible(self.request.user)\n        return rows if self.action == "list" else rows.prefetch_related(*[item["name"] for item in SCHEMA["details"]])')
            value = value.replace("    ordering_fields = ['created_at', 'updated_at']", '    ordering_fields = ' + repr(['id', 'created_at', 'updated_at', *[field['name'] for field in definition.fields if field['sortable']]]))
            value = value.replace("    ordering = ['-created_at', '-id']", '    ordering = ' + repr(list(definition.ordering)))
            value = value.replace("'destroy': '" + module + ":delete'}", "'destroy': '" + module + ":delete', 'choices': '" + module + ":read'}")
            if definition.approval:
                value = value.replace("'choices': '" + module + ":read'}", "'choices': '" + module + ":read', 'submit': '" + module + ":submit', 'withdraw': '" + module + ":withdraw'}")
        if name == 'module.md':
            value = value[:value.index('仅支持有界文本')]
            value += '\nV2 支持单表/树表/主子表。字段、查询、控件及排序以 schema.py 为准。关联对象由服务端重新核验权限和数据范围；附件只引用已上传且有权访问的一般文件。\n\n主子表提交每组完整明细，省略分组表示保留（PATCH）；提交数组表示整体替换，明细ID不作为编辑契约，主记录version控制整单并发。默认只允许表单配置开启的字段写入，计算字段在 extensions.py 中实现。\n\n**手写文件**：extensions.py 与 RecordListView.vue 只允许首次创建；计划将现有文件标为 preserved，再次应用不要选择它们。其他文件由生成器管理，修改前先转移业务逻辑到扩展。禁止用ZIP直接覆盖已有模块；使用CLI预览和逐文件选择。\n\n树表采用父节点筛选逐层浏览，服务端串行检查移动并拒绝环及删除有子节点的记录。字典变更不改写历史记录；再次提交失效值时返回校验错误。关联目标必须是已登记且启用的生成模块，不允许指向认证、权限等内部模型。\n'
        if name == 'module.md' and definition.approval:
            value += ('\n审批接入：依赖 approvals 模块，创建并审查 approval_status / approval_request 字段迁移，'
                      '初始化后分配本模块 submit / withdraw 权限。发布与 schema.py 中 flow_code 匹配的 V2 流程，'
                      '输入仅从同名同类型主表字段读取。提交/撤回只传 version；仅创建人可操作。'
                      '审批中和已通过禁止编辑，存在审批历史禁止删除；结果由审批中心在同一事务中回写。'
                      '审批参与人可读取提交时的字段/明细快照。\n')
        if name == 'module.md' and definition.reports:
            value += ('\n报表接入：开启 reports 模块后自动发现已登记的维度/指标/筛选字段，'
                      '运行仍需本模块 read 权限并继承业务数据范围和租户边界；不支持任意模型或关联路径。\n')
        files[(f'docs/generated/{module}.md' if name == 'module.md' else root + name)] = value
    page_root = f'frontend/src/views/{module}/'
    files[page_root + 'GeneratedPage.vue'] = '<template><GeneratedCrudPage :schema="schema"><slot /></GeneratedCrudPage></template>\n<script setup lang="ts">\nimport GeneratedCrudPage from "@/components/codegen/GeneratedCrudPage.vue"\nimport type { GeneratedSchema } from "@/components/codegen/types"\nconst schema: GeneratedSchema = ' + script_json(schema) + '\n</script>\n'
    files[page_root + 'RecordListView.vue'] = '<!-- 手写入口：生成器只首次创建，可添加业务工具栏/说明。 -->\n<template><GeneratedPage /></template>\n<script setup lang="ts">\nimport GeneratedPage from "./GeneratedPage.vue"\n</script>\n'
    files[f'backend/tests/test_generated_{module}.py'] = f'''"""基础接入契约；项目需另补真实业务样例的CRUD与并发验收。"""
import pytest
from django.urls import path, include
from config.urls import urlpatterns as base_urls
from apps.{module}.models import {model}
from apps.{module}.schema import SCHEMA

pytestmark = pytest.mark.django_db
URL = '/api/v1/{module.replace('_', '-')}/records/'
urlpatterns = list(base_urls) + [path('api/v1/{module.replace('_', '-')}/', include('apps.{module}.urls'))]


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = tuple(dict.fromkeys((*settings.ADMINCORE_MODULES, {module!r})))
    settings.ROOT_URLCONF = __name__


def test_list_query_and_write_whitelist(admin_client):
    assert admin_client.get(URL).status_code == 200
    for params in [{{'unknown': '1'}}, {{'ordering': 'creator__username'}}]:
        assert admin_client.get(URL, params).status_code == 400
    assert admin_client.post(URL, {{'version': 0, 'creator': 'spoof'}}, format='json').status_code == 400
    assert not {model}.objects.exists()


def test_reader_permission_required(member_client):
    assert member_client.get(URL).status_code == 403


def test_generated_model_fields():
    for spec in SCHEMA['fields']:
        assert {model}._meta.get_field(spec['name']) is not None
'''
    for path, content in files.items():
        if path.endswith('.py'):
            ast.parse(content, filename=path)
    return files
