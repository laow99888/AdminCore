"""显式登记的生成业务只读能力；不接受客户端模型名、导入路径或自定义查询。"""
from importlib import import_module

from django.apps import apps
from rest_framework.exceptions import NotFound

from apps.core.codegen.integrations import registered_module
from apps.core.modules import module_enabled


def registered_business_resources():
    from apps.core.modules import MODULES
    result = {}
    for module in MODULES:
        if (not module_enabled(module.key) or not apps.is_installed('apps.' + module.key)
                or module.key not in {key for key, _ in module.field_policies}):
            continue
        manifest = import_module('apps.' + module.key + '.manifest')
        if getattr(manifest, 'API_CAPABILITIES', None) != ('read',):
            continue
        try:
            schema, model, service = registered_module(module.key)
        except NotFound:
            continue
        # 只认可生成器真实登记的字段策略资源，不将普通 Django 模型变成开放接口。
        result[module.key] = (schema, model, service)
    return result
