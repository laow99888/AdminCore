"""列表/导出单条 SQL 的局部预算，不改变迁移、后台任务或连接默认值。"""
from contextlib import contextmanager

from django.conf import settings
from django.db import DatabaseError, connections, transaction

from .exceptions import APIError
from .tenancy import TenantQuerysetMixin


@contextmanager
def query_budget(using='default'):
    connection = connections[using]
    if connection.vendor != 'postgresql':
        yield
        return
    try:
        with transaction.atomic(using=using):
            with connection.cursor() as cursor:
                cursor.execute("SELECT name, setting FROM pg_settings "
                               "WHERE name IN ('statement_timeout', 'lock_timeout')")
                previous = dict(cursor.fetchall())  # 两项 setting 的单位均为毫秒。
                limits = [settings.ADMINCORE_QUERY_STATEMENT_TIMEOUT_MS,
                          settings.ADMINCORE_QUERY_LOCK_TIMEOUT_MS]
                for index, name in enumerate(['statement_timeout', 'lock_timeout']):
                    existing = int(previous[name])
                    if existing:
                        limits[index] = min(limits[index], existing)
                cursor.execute("SELECT set_config('statement_timeout', %s, true), "
                               "set_config('lock_timeout', %s, true)",
                               [str(limit) for limit in limits])
            yield
            # SET LOCAL 在成功的内层 savepoint 释放后仍会保留；显式恢复外层预算。
            if not connection.needs_rollback:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('statement_timeout', %s, true), "
                                   "set_config('lock_timeout', %s, true)",
                                   [previous['statement_timeout'], previous['lock_timeout']])
    except DatabaseError as exc:
        # 先退出 atomic 回滚，再转换响应，确保长连接/外层事务仍可查询。
        cause = exc.__cause__
        state = getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)
        if state in {'57014', '55P03'}:
            raise APIError('查询超时或等待锁过久，请缩小筛选范围后重试', status_code=503) from None
        raise


class QueryBudgetListMixin(TenantQuerysetMixin):
    # 未声明时不向客户端开放排序，禁止 DRF 按 serializer 字段隐式扩大白名单。
    ordering_fields = ()
    list_query_choices = {}

    def list(self, request, *args, **kwargs):
        from .list_queries import validate_list_query
        validate_list_query(request, self)
        with query_budget():
            return super().list(request, *args, **kwargs)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if getattr(self, 'action', None) == 'list':
            from .list_queries import stable_ordering
            queryset = stable_ordering(queryset)
        return queryset
