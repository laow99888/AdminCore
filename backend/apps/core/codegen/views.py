"""在线生成只在内存中预览/打包，不写服务器源码、不安装模块。"""
from io import BytesIO
import json
import zipfile
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from apps.permissions.permissions import HasPermission, IsAdmin
from .spec import GenerationError, parse_definition
from .render import render


class GenerationRequest(serializers.Serializer):
    definition = serializers.JSONField()


class GenerationPreview(serializers.Serializer):
    definition = serializers.JSONField()
    files = serializers.ListField(child=serializers.DictField(child=serializers.CharField()))


class GenerationThrottle(UserRateThrottle):
    scope = 'codegen'
    rate = '20/min'


class GenerationView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'codegen:generate'
    throttle_classes = [GenerationThrottle]

    def generate(self, request):
        serializer = GenerationRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw = serializer.validated_data['definition']
        if len(json.dumps(raw, ensure_ascii=False).encode()) > 128 * 1024:
            raise ValidationError('业务定义最多128KB')
        if not isinstance(raw, dict) or raw.get('schema_version') != 2:
            raise ValidationError('在线配置必须使用V2定义')
        try:
            definition = parse_definition(raw)
            files = render(definition)
        except GenerationError as error:
            raise ValidationError(str(error)) from error
        if sum(len(value.encode()) for value in files.values()) > 2 * 1024 * 1024:
            raise ValidationError('生成产物超过2MB，请减少字段或明细组')
        return definition, files

    @extend_schema(request=GenerationRequest, responses=GenerationPreview)
    def post(self, request):
        definition, files = self.generate(request)
        response = Response({'definition': definition.as_dict(), 'files': [{'path': name, 'content': content} for name, content in sorted(files.items())]})
        response['Cache-Control'] = 'private, no-store'
        return response


class GenerationDownloadView(GenerationView):
    @extend_schema(request=GenerationRequest, responses={(200, 'application/zip'): OpenApiTypes.BINARY})
    def post(self, request):
        definition, files = self.generate(request)
        output = BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            files['codegen-definition.json'] = json.dumps(definition.as_dict(), ensure_ascii=False, indent=2)
            for name, content in sorted(files.items()):
                archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), content.encode(), compress_type=zipfile.ZIP_DEFLATED)
        response = HttpResponse(output.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{definition.module}-source.zip"'
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
