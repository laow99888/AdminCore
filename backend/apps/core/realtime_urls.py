"""WSGI 不占用同步 worker 承载长连接；启用时提示独立服务未接入。"""
from django.http import JsonResponse
from django.urls import path


def unavailable(request):
    return JsonResponse({'code': 503, 'message': '实时通道服务未接入', 'data': None}, status=503,
                        headers={'Cache-Control': 'private, no-store', 'Retry-After': '60'})


urlpatterns = [path('events/', unavailable, name='realtime-events')]
