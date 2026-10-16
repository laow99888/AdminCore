from django.http import JsonResponse
from rest_framework.exceptions import APIException
from .services import enforce


class IPPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 仅精确豁免存活/就绪探针；API、认证、后台和预检自身全部受限。
        if request.path not in {'/api/v1/health/', '/api/v1/health/live/'}:
            try:
                enforce(request)
            except APIException as error:
                response = JsonResponse({'code': error.status_code, 'message': str(error.detail), 'data': None}, status=error.status_code)
                response['Cache-Control'] = 'private, no-store'
                if error.status_code == 503:
                    response['Retry-After'] = '60'
                return response
        return self.get_response(request)
