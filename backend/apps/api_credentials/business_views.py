"""只复用生成业务的读取协议；审批、批量、导入及写入路由没有挂载。"""
from importlib import import_module

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.codegen.runtime import GeneratedViewMixin
from apps.core.query_budget import query_budget
from .business import registered_business_resources
from .views import GatewayBase


@extend_schema_view(
    list=extend_schema(operation_id='api_credentials_business_records_list', responses=OpenApiTypes.OBJECT, description='读取显式登记业务资源；字段、筛选、排序和数据范围复用该业务协议。'),
    retrieve=extend_schema(operation_id='api_credentials_business_records_retrieve', responses=OpenApiTypes.OBJECT, description='按当前权限读取业务整单；附件引用不授予下载权限。'),
)
class BusinessGatewayViewSet(GeneratedViewMixin, GatewayBase):
    serializer_class = serializers.Serializer

    @property
    def generated_query_parameters(self):
        # 文档是动态资源入口，不在 schema 构建期解析用户提供的资源路径。
        if getattr(self, 'swagger_fake_view', False):
            return ()
        return super().generated_query_parameters

    def initial(self, request, *args, **kwargs):
        resource = self.kwargs['resource']
        registered = registered_business_resources().get(resource)
        if registered is None:
            raise NotFound()
        self.generated_schema, _, self.generated_service = registered
        self.credential_scope = resource + ':read'
        # 路径只来自上述闭集，不使用请求提供的 Python 名称。
        generated = import_module('apps.' + resource + '.views').RecordViewSet
        self.record_serializer = generated.serializer_class
        self.list_serializer = import_module('apps.' + resource + '.serializers').__dict__[
            self.generated_schema['model'] + 'ListSerializer']
        for name in ('search_fields', 'ordering_fields', 'ordering'):
            setattr(self, name, getattr(generated, name))
        super().initial(request, *args, **kwargs)

    def get_serializer_class(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.serializer_class
        return self.list_serializer if self.action == 'list' else self.record_serializer

    def get_queryset(self):
        rows = self.generated_service.visible(self.request.user)
        if self.action != 'list':
            rows = rows.prefetch_related(*[group['name'] for group in self.generated_schema['details']])
        return rows

    def retrieve(self, request, *args, **kwargs):
        # 详情不静默忽略筛选/模型/字段探测参数，也不允许无限展开任意关系。
        if request.query_params:
            raise ValidationError('业务详情不接受查询参数')
        with query_budget():
            return super().retrieve(request, *args, **kwargs)
