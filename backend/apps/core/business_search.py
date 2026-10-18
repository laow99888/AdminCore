"""显式登记的生成业务搜索；查询、摘要及跳转不接受客户端提供模型或路径。"""
from importlib import import_module

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.codegen.integrations import registered_module
from apps.core.query_budget import query_budget
from apps.core.schema import MessageResponse, envelope
from apps.core.tenancy import current_tenant_id, enabled
from apps.permissions.field_permissions import business_allowed_fields
from apps.permissions.permissions import has_permission_code

MAX_SOURCES = 8
PER_SOURCE = 5


class SearchValueSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.CharField()


class SearchRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    values = SearchValueSerializer(many=True)


class SearchSourceSerializer(serializers.Serializer):
    source = serializers.CharField()
    title = serializers.CharField()
    path = serializers.CharField()
    items = SearchRecordSerializer(many=True)
    has_more = serializers.BooleanField()


class BusinessSearchResultSerializer(serializers.Serializer):
    groups = SearchSourceSerializer(many=True)
    sources_limited = serializers.BooleanField()


def sources(actor):
    from apps.core.modules import MODULES, module_enabled
    for module in MODULES:
        if not module_enabled(module.key) or not has_permission_code(actor, module.key + ':read'):
            continue
        try:
            schema, _, service = registered_module(module.key)
        except NotFound:
            continue
        declaration = getattr(import_module('apps.' + module.key + '.manifest'), 'BUSINESS_SEARCH', None)
        if not isinstance(declaration, dict) or set(declaration) != {'fields', 'title_field'}:
            continue
        names = declaration['fields']
        fields = {field['name']: field for field in schema['fields']
                  if field['kind'] == 'string' and field['query'] in {'eq', 'contains'}}
        # 配置错误关闭该来源；禁止任意 lookup、关联标签、正文或明细隐式参与匹配。
        if (not isinstance(names, (list, tuple)) or not 1 <= len(names) <= 3
                or any(not isinstance(name, str) or name not in fields for name in names)
                or len(set(names)) != len(names) or declaration['title_field'] not in names):
            continue
        menu = next((menu for menu in module.menus if menu.permission == module.key + ':read'
                     and menu.path in module.paths and menu.path.startswith('/') and not menu.path.startswith('//')), None)
        if menu is None:
            continue
        allowed = business_allowed_fields(actor, module.key, 'read')
        readable = [fields[name] for name in names if allowed is None or name in allowed]
        if readable:
            yield module, schema, service, menu.path, readable, declaration['title_field']


def search(actor, query, source=None):
    registered = list(sources(actor))
    if source:
        registered = [item for item in registered if item[0].key == source]
        if not registered:
            raise NotFound()
    limited = len(registered) > MAX_SOURCES
    groups = []
    # 平台管理员没有选择租户时也不跨租户聚合业务记录。
    if enabled() and current_tenant_id() is None:
        return {'groups': [], 'sources_limited': limited}
    with query_budget():
        for module, schema, service, path, fields, title_field in registered[:MAX_SOURCES]:
            condition = Q(pk__in=[])
            for field in fields:
                condition |= Q(**{field['name'] + ('__icontains' if field['query'] == 'contains' else ''): query})
            rows = service.visible(actor)
            if enabled():
                rows = rows.filter(tenant_id=current_tenant_id())
            records = list(rows.filter(condition).order_by('-created_at', '-pk').values('pk', *[field['name'] for field in fields])[:PER_SOURCE + 1])
            items = [{'id': str(row['pk']),
                      'title': str(row.get(title_field) or schema['title'])[:160],
                      'values': [{'label': field['label'], 'value': str(row[field['name']] or '')[:160]} for field in fields]}
                     for row in records[:PER_SOURCE]]
            if items:
                groups.append({'source': module.key, 'title': schema['title'], 'path': path,
                               'items': items, 'has_more': len(records) > PER_SOURCE})
    return {'groups': groups, 'sources_limited': limited}


class BusinessSearchView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter('q', str, required=True, description='2至80字符；只匹配显式登记且当前可读的文本字段'),
                               OpenApiParameter('source', str, description='可选：限定已授权的来源编码')],
                   responses={200: envelope('BusinessSearchResponse', BusinessSearchResultSerializer()),
                              400: MessageResponse, 404: MessageResponse, 503: MessageResponse})
    def get(self, request):
        params = request.query_params
        query = params.get('q', '').strip()
        if (set(params) - {'q', 'source'} or any(len(params.getlist(key)) != 1 for key in params)
                or not 2 <= len(query) <= 80 or '\x00' in query
                or ('source' in params and (not params['source'] or len(params['source']) > 80))):
            raise ValidationError('业务搜索需要2至80个字符，且只支持q和source参数')
        result = search(request.user, query, params.get('source'))
        response = Response({'code': 200, 'message': 'success', 'data': result})
        response['Cache-Control'] = 'no-store'
        return response
