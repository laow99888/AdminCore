"""标准列表查询边界；资源过滤类型仍由 DjangoFilterBackend 校验。"""
from rest_framework.exceptions import ValidationError

MAX_QUERY_VALUE_LENGTH = 200
MAX_ORDERING_FIELDS = 5


def allowed_query_parameters(view):
    names = {'page', 'page_size', 'format'}
    names.update(getattr(view, 'filterset_fields', ()) or ())
    filterset = getattr(view, 'filterset_class', None)
    if filterset:
        names.update(filterset.base_filters)
    if getattr(view, 'search_fields', ()):
        names.add('search')
    if view.ordering_fields:
        names.add('ordering')
    names.update(view.list_query_choices)
    return names


def validate_list_query(request, view):
    params = request.query_params
    if set(params) - allowed_query_parameters(view):
        raise ValidationError({'query': '存在不支持的查询参数'})
    if any(len(params.getlist(key)) != 1 for key in params):
        raise ValidationError({'query': '查询参数不能重复'})
    if any(len(value) > MAX_QUERY_VALUE_LENGTH for value in params.values()):
        raise ValidationError({'query': '查询参数最多200个字符'})
    if any('\x00' in value for value in params.values()):
        raise ValidationError({'query': '查询参数包含无效字符'})
    for name, choices in view.list_query_choices.items():
        if name in params and params[name] not in choices:
            raise ValidationError({name: '查询选项无效'})
    ordering = params.get('ordering', '')
    if ordering:
        fields = [field.strip() for field in ordering.split(',')]
        if len(fields) > MAX_ORDERING_FIELDS:
            raise ValidationError({'ordering': '最多允许5个排序字段'})
        names = [field.removeprefix('-') for field in fields]
        if any(name not in view.ordering_fields for name in names):
            raise ValidationError({'ordering': '排序字段不受支持'})
        if len(set(names)) != len(names):
            raise ValidationError({'ordering': '排序字段不能重复'})


def stable_ordering(queryset):
    """同值记录以主键收尾；不提供跨请求数据库快照或游标分页承诺。"""
    ordering = list(queryset.query.order_by)
    if not ordering and queryset.query.default_ordering:
        ordering = list(queryset.model._meta.ordering or ())
    primary_key = queryset.model._meta.pk
    aliases = {'pk', primary_key.name, primary_key.attname}
    if not any(isinstance(field, str) and field.removeprefix('-') in aliases for field in ordering):
        ordering.append('pk')
    return queryset.order_by(*ordering)
