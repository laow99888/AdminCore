"""请求级读写分离、写后读一致性和副本故障回退。"""

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from asgiref.sync import sync_to_async
from django.db import DatabaseError, connections

from config import db_router


class DatabaseRoutingMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def _prepare(self, request):
        sticky = db_router.has_valid_sticky_cookie(
            request.COOKIES.get(db_router.STICKY_COOKIE, ""))
        return db_router.start_request(request.method, sticky)

    def process_exception(self, request, exception):
        if isinstance(exception, DatabaseError) and db_router.should_fallback():
            from django.http import JsonResponse
            response = JsonResponse({'code': 503, 'message': '只读服务暂不可用', 'data': None}, status=503)
            response._admincore_replica_failure = True
            return response

    @staticmethod
    def _close_replica():
        if db_router.REPLICA_ALIAS in connections.databases:
            connections[db_router.REPLICA_ALIAS].close()

    def _finish(self, request, response, token):
        state = db_router.current_state()
        try:
            if (state and state["method"] not in {"GET", "HEAD", "OPTIONS"}
                    and 200 <= response.status_code < 400):
                value, seconds = db_router.sticky_cookie_value()
                response.set_cookie(db_router.STICKY_COOKIE, value, max_age=seconds,
                                    httponly=True, samesite="Lax",
                                    secure=request.is_secure())
            return response
        finally:
            db_router.finish_request(token)

    def __call__(self, request):
        if self.is_async:
            return self.async_call(request)
        token = self._prepare(request)
        try:
            try:
                response = self.get_response(request)
            except DatabaseError:
                if not db_router.should_fallback():
                    raise
                db_router.force_primary()
                self._close_replica()
                response = self.get_response(request)
                response["X-AdminCore-Read-Replica-Fallback"] = "primary"
            if getattr(response, '_admincore_replica_failure', False) and db_router.should_fallback():
                db_router.force_primary()
                self._close_replica()
                response = self.get_response(request)
                response['X-AdminCore-Read-Replica-Fallback'] = 'primary'
            return self._finish(request, response, token)
        except Exception:
            db_router.finish_request(token)
            raise

    async def async_call(self, request):
        token = self._prepare(request)
        try:
            try:
                response = await self.get_response(request)
            except DatabaseError:
                if not db_router.should_fallback():
                    raise
                db_router.force_primary()
                await sync_to_async(self._close_replica, thread_sensitive=True)()
                response = await self.get_response(request)
                response["X-AdminCore-Read-Replica-Fallback"] = "primary"
            if getattr(response, '_admincore_replica_failure', False) and db_router.should_fallback():
                db_router.force_primary()
                await sync_to_async(self._close_replica, thread_sensitive=True)()
                response = await self.get_response(request)
                response['X-AdminCore-Read-Replica-Fallback'] = 'primary'
            return self._finish(request, response, token)
        except Exception:
            db_router.finish_request(token)
            raise
