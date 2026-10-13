from django.http import JsonResponse
from .modules import MODULES, module_enabled


class ModuleGateMiddleware:
    """包括已有 URL 缓存及 Django admin 的关闭入口，禁用后仍保留数据。"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        for module in MODULES:
            if not module_enabled(module.key) and (
                request.path.startswith(f'/api/v1/{module.api_prefix}/')
                or request.path.startswith(f'/admin/{module.key}/')
            ):
                return JsonResponse({'code': 404, 'message': '模块未启用', 'data': None}, status=404)
        return self.get_response(request)
