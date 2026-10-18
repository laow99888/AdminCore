"""以真实 PROTECT 外键作为引用事实；不复制业务行，也不公开业务标识。

关联写入方须在事务内先锁定并复核文件，再写入外键。生成业务及审批提交
遵守此协议；删除方持有同一文件行锁，避免检查与删除之间新增引用。
"""
from django.db.models import Exists, OuterRef, Q
from django.db.models.deletion import PROTECT

from apps.core.models import LifecycleConflict


def unreferenced_files(queryset):
    # include_hidden 包含生成器 related_name='+' 的主表和明细附件字段。
    # _base_manager 不受当前租户过滤：隐藏或停用模块的历史引用也必须保护。
    condition = Q()
    for relation in queryset.model._meta.get_fields(include_hidden=True):
        if (relation.auto_created and not relation.concrete
                and (relation.one_to_many or relation.one_to_one)
                and relation.field.remote_field.on_delete is PROTECT):
            related = relation.related_model._base_manager.filter(**{relation.field.attname: OuterRef('pk')})
            condition |= Q(Exists(related))
    return queryset.exclude(condition) if condition else queryset


def is_referenced(file):
    return not unreferenced_files(type(file)._base_manager.filter(pk=file.pk)).exists()


def assert_not_referenced(file):
    if is_referenced(file):
        raise LifecycleConflict('文件仍被业务记录或历史快照引用，不能删除；请先在来源业务中处理引用')
