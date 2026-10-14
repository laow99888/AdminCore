from django.core.cache.backends.locmem import LocMemCache
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.permissions.permissions import IsAdmin, HasPermission
from . import cache_management as manager
from .schema import envelope


class CacheThrottle(UserRateThrottle):
    cache = LocMemCache('admincore-cache-management', {'OPTIONS': {'MAX_ENTRIES': 1024}})
    rate = '20/min'
    scope = 'cache_management'


class NamespaceSerializer(serializers.Serializer):
    namespace = serializers.ChoiceField(choices=list(manager.NAMESPACES))
    module = serializers.CharField()
    candidate_count = serializers.IntegerField()
    over_limit = serializers.BooleanField()


class CatalogSerializer(serializers.Serializer):
    backend = serializers.ChoiceField(choices=['shared', 'in_process', 'unsupported'])
    limit = serializers.IntegerField()
    ttl_seconds = serializers.IntegerField()
    namespaces = NamespaceSerializer(many=True)


class PreviewRequest(serializers.Serializer):
    namespace = serializers.ChoiceField(choices=list(manager.NAMESPACES))

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError('请求包含未允许的字段')
        return attrs


class ClearRequest(PreviewRequest):
    token = serializers.CharField(max_length=1000, trim_whitespace=False)


class ClearResult(serializers.Serializer):
    namespace = serializers.CharField()
    candidate_count = serializers.IntegerField()
    backend = serializers.CharField()
    outcome = serializers.CharField()


class PreviewResult(serializers.Serializer):
    namespace = serializers.CharField()
    candidate_count = serializers.IntegerField()
    backend = serializers.CharField()
    expires_in = serializers.IntegerField()
    token = serializers.CharField()


class CacheCatalogView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'cache:read'
    throttle_classes = [CacheThrottle]
    http_method_names = ['get', 'head', 'options']

    @extend_schema(responses=envelope('CacheCatalogResponse', CatalogSerializer()))
    def get(self, request):
        rows = []
        for namespace in manager.NAMESPACES:
            count = len(manager.candidates(namespace))
            rows.append({'namespace': namespace, 'module': 'system', 'candidate_count': min(count, manager.LIMIT),
                         'over_limit': count > manager.LIMIT})
        return Response({'code': 200, 'message': 'success', 'data': {'backend': manager.backend_mode(),
                         'limit': manager.LIMIT, 'ttl_seconds': 300, 'namespaces': rows}},
                        headers={'Cache-Control': 'private, no-store'})


class CachePreviewView(CacheCatalogView):
    required_permission = 'cache:clear'
    http_method_names = ['post', 'options']

    @extend_schema(request=PreviewRequest, responses=envelope('CachePreviewResponse', PreviewResult()))
    def post(self, request):
        serializer = PreviewRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = manager.preview(request, serializer.validated_data['namespace'])
        return Response({'code': 200, 'message': 'success', 'data': data}, headers={'Cache-Control': 'private, no-store'})


class CacheClearView(CachePreviewView):
    @extend_schema(request=ClearRequest, responses=envelope('CacheClearResponse', ClearResult()))
    def post(self, request):
        serializer = ClearRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = manager.clear(request, **serializer.validated_data)
        return Response({'code': 200, 'message': 'success', 'data': data}, headers={'Cache-Control': 'private, no-store'})
