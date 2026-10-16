"""为会话认证、测试认证和后台请求建立租户上下文。"""
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from rest_framework.exceptions import APIException
from .tenancy import activate_for_user

class TenantContextMiddleware(MiddlewareMixin):
    def process_request(self, request):
        user = getattr(request, '_force_auth_user', None) or getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return None
        try:
            activate_for_user(request, user)
        except APIException as exc:
            detail = exc.detail if hasattr(exc, 'detail') else str(exc)
            return JsonResponse({'code': exc.status_code, 'message': detail, 'data': None}, status=exc.status_code)
        return None
