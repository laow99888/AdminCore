"""容器内部探针：HTTPS 网关模式下仍能检查本机 Django。"""
import json
import os
from urllib.request import Request, urlopen

host = next((value.strip() for value in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')
             if value.strip() and value.strip() != '*'), 'localhost')
headers = {'Host': host}
if os.getenv('USE_TLS', 'False').lower() == 'true':
    headers['X-Forwarded-Proto'] = 'https'
with urlopen(Request('http://127.0.0.1:8000/api/v1/health/', headers=headers), timeout=4) as response:
    assert json.load(response).get('status') == 'ok'
