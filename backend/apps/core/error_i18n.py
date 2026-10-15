"""只翻译服务端消息和 DRF 错误详情，不改业务字段、代码或持久化内容。"""
import json
from pathlib import Path

from django.utils.translation import get_language
from django.utils.deprecation import MiddlewareMixin
from rest_framework.exceptions import ErrorDetail

ENGLISH = json.loads((Path(__file__).parent / 'error_messages.en.json').read_text(encoding='utf-8'))


def error_text(message, **values):
    text = ENGLISH.get(message, message) if (get_language() or '').startswith('en') else message
    return text.format(**values) if values else text


def error_details(value):
    if isinstance(value, ErrorDetail):
        return ErrorDetail(error_text(str(value)), code=value.code)
    if isinstance(value, dict):
        return {key: error_details(item) for key, item in value.items()}
    if isinstance(value, list):
        return [error_details(item) for item in value]
    return value


class APIErrorI18nMiddleware(MiddlewareMixin):
    def process_template_response(self, request, response):
        if request.path.startswith('/api/') and isinstance(getattr(response, 'data', None), dict):
            data = dict(response.data)
            if isinstance(data.get('message'), str):
                data['message'] = error_text(data['message'])
            if response.status_code >= 400:
                data = error_details(data)
            response.data = data
        return response

    def process_response(self, request, response):
        # 模块门禁等 JsonResponse 不经过 DRF 模板渲染；仅翻译其固定 message。
        if (request.path.startswith('/api/') and not response.streaming
                and not hasattr(response, 'data') and response.status_code >= 400
                and response.get('Content-Type', '').split(';')[0] == 'application/json'
                and len(response.content) <= 65536):
            try:
                data = json.loads(response.content)
            except (ValueError, UnicodeDecodeError):
                return response
            if isinstance(data, dict) and isinstance(data.get('message'), str):
                localized = error_text(data['message'])
                if localized != data['message']:
                    data['message'] = localized
                    response.content = json.dumps(data, ensure_ascii=False).encode('utf-8')
                    if response.has_header('Content-Length'):
                        response['Content-Length'] = str(len(response.content))
        return response
