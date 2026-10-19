"""HTTP 结果审计在业务事务退出后写入，失败时补偿本次新产生的文件。"""
import logging

from django.db import transaction
from django.http import JsonResponse

from .antivirus import scan_context


def persist_scan_results(request):
    """可在业务事务提交前调用，避免失败补偿破坏已经发布的引用。"""
    context = scan_context.get()
    if not context or not context['results']:
        return
    results = list(context['results'])
    with transaction.atomic():
        from apps.logs.audit import write_audit
        for result, identifier in results:
            write_audit(request=request, resource='file_scan', identifier=identifier, action='other',
                        after=result, status=200 if result['outcome'] == 'clean' else 422)
    del context['results'][:len(results)]


class ScanAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        context = {'results': [], 'artifacts': []}
        token = scan_context.set(context)
        try:
            response = self.get_response(request)
            # 无扫描的健康检查、认证失败和普通列表请求不应触碰数据库事务。
            if not context['results']:
                return response
            try:
                # 只包住审计写入，避免给整个请求增加 SAVEPOINT 和查询开销。
                persist_scan_results(request)
            except Exception:
                for artifact in context['artifacts']:
                    storage, name, instance = artifact
                    try:
                        if instance is not None and getattr(instance, 'pk', None):
                            instance.delete()
                    except Exception:
                        logging.getLogger(__name__).error('Failed to clean database artifact after scan audit failure',
                                                          extra={'event': 'file.scan_audit_failed'})
                    try:
                        storage.delete(name)
                    except Exception:
                        logging.getLogger(__name__).error('Failed to clean upload after scan audit failure',
                                                          extra={'event': 'file.scan_audit_failed'})
                logging.getLogger(__name__).error('File scan audit failed', extra={'event': 'file.scan_audit_failed'})
                response.close()
                response = JsonResponse({'code': 503, 'message': '文件扫描审计暂时不可用，文件未放行', 'data': None}, status=503)
                response['Cache-Control'] = 'private, no-store'
            return response
        finally:
            scan_context.reset(token)
