from django.core.cache import cache
from django.db import transaction, IntegrityError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.permissions.permissions import HasPermission
from .mixins import EnvelopeResponseMixin
from .schema import envelope
from .models import SystemConfig, DataDictionary
from .cache_keys import dictionary_cache_key
from .system_config import config_value, visible_definitions
from .system_serializers import ConfigWriteSerializer, ConfigRowSerializer, DictionarySerializer, DictionaryOptionsSerializer, BrandSerializer


class VersionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = '内容已被其他人修改，请刷新后重试'


def audit(request, resource, identifier, before, after):
    record = None
    if resource == 'maintenance_run':
        from apps.tasks.models import TaskRecord
        record = TaskRecord.objects.get(pk=identifier)
    if resource == 'system_config' and identifier == 'brand.logo':
        import hashlib
        before, after = [hashlib.sha256(value.encode()).hexdigest() if value else None for value in (before, after)]
    action = 'create' if before is None else 'delete' if after is None else 'update'
    from apps.logs.audit import write_audit
    if resource == 'system_config':
        before, after = {'value': before}, {'value': after}
    write_audit(request=request, action=action, resource=resource, identifier=identifier,
                before=before, after=after, record=record)


class SystemConfigView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'get': 'config:read', 'patch': 'config:update'}

    @extend_schema(operation_id='system_config_detail', responses=envelope('SystemConfigDetailResponse', ConfigRowSerializer(many=True)))
    def get(self, request, key=None):
        allowed = visible_definitions()
        if key is not None and key not in allowed:
            raise NotFound()
        rows = {row.key: row for row in SystemConfig.objects.all()}
        definitions = [allowed[key]] if key else allowed.values()
        data = [{'key': definition.key, 'label': definition.label, 'kind': definition.kind,
                 'value': rows[definition.key].value if definition.key in rows else definition.default_value(),
                 'default': definition.default_value(), 'version': rows[definition.key].version if definition.key in rows else 0,
                 'minimum': definition.minimum, 'maximum': definition.maximum,
                 'effective': '下次读取生效；品牌在页面刷新后生效'} for definition in definitions]
        return Response({'code': 200, 'message': 'success', 'data': data})

    @extend_schema(operation_id='system_config_write', request=ConfigWriteSerializer, responses=envelope('SystemConfigWriteResponse', ConfigRowSerializer(many=True)))
    def patch(self, request, key=None):
        definition = visible_definitions().get(key)
        if definition is None:
            raise NotFound()
        serializer = ConfigWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = definition.validate(serializer.validated_data['value'])
        expected = serializer.validated_data['version']
        try:
            with transaction.atomic():
                row = SystemConfig.objects.select_for_update().filter(key=key).first()
                if expected != (row.version if row else 0):
                    raise VersionConflict()
                before = row.value if row else definition.default_value()
                if row:
                    row.value, row.version, row.updated_by = value, row.version + 1, request.user
                    row.save()
                else:
                    row = SystemConfig.objects.create(key=key, value=value, updated_by=request.user)
                audit(request, 'system_config', key, before, value)
        except IntegrityError as exc:
            raise VersionConflict() from exc
        return self.get(request, key)


class SystemConfigListView(SystemConfigView):
    http_method_names = ['get', 'head', 'options']

    @extend_schema(operation_id='system_config_list', responses=envelope('SystemConfigListResponse', ConfigRowSerializer(many=True)))
    def get(self, request):
        return super().get(request)


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('DictionaryDetailResponse', DictionarySerializer())),
    create=extend_schema(responses={201: envelope('DictionaryCreatedResponse', DictionarySerializer())}),
    update=extend_schema(responses=envelope('DictionaryUpdatedResponse', DictionarySerializer())),
    partial_update=extend_schema(responses=envelope('DictionaryPatchedResponse', DictionarySerializer())),
)
class DictionaryViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    queryset = DataDictionary.objects.all()
    serializer_class = DictionarySerializer
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'dictionary:read', 'retrieve': 'dictionary:read', 'create': 'dictionary:update',
                      'update': 'dictionary:update', 'partial_update': 'dictionary:update', 'destroy': 'dictionary:update', 'choices': 'dictionary:read'}
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    search_fields = ['name', 'code']
    filterset_fields = ['is_active']
    ordering_fields = ['code', 'created_at']
    ordering = ['code']

    @transaction.atomic
    def perform_create(self, serializer):
        if serializer.validated_data['version'] != 0:
            raise ValidationError({'version': '新建字典版本必须为 0'})
        try:
            with transaction.atomic():
                row = serializer.save(version=1)
        except IntegrityError as exc:
            raise VersionConflict() from exc
        audit(self.request, 'dictionary', row.pk, None, DictionarySerializer(row).data)

    @transaction.atomic
    def perform_update(self, serializer):
        current = DataDictionary.objects.select_for_update().get(pk=serializer.instance.pk)
        expected = serializer.validated_data.get('version')
        if expected is None:
            raise ValidationError({'version': '更新必须传入当前版本'})
        if expected != current.version:
            raise VersionConflict()
        before = DictionarySerializer(current).data
        serializer.instance = current
        row = serializer.save(version=current.version + 1)
        audit(self.request, 'dictionary', row.pk, before, DictionarySerializer(row).data)

    @extend_schema(responses=envelope('DictionaryOptionsResponse', DictionaryOptionsSerializer()), filters=False)
    @action(detail=False, url_path=r'options/(?P<code>[a-z][a-z0-9_]{0,63})', methods=['get'], permission_classes=[IsAuthenticated])
    def choices(self, request, code=None):
        row = DataDictionary.objects.filter(code=code, is_active=True).first()
        if row is None:
            raise NotFound()
        key = dictionary_cache_key(row.id, row.version)
        items = cache.get(key)
        if items is None:
            items = sorted([item for item in row.items if item['is_active']], key=lambda item: item['order'])
            cache.set(key, items, timeout=300)
        return Response({'code': 200, 'message': 'success', 'data': {'code': row.code, 'version': row.version, 'items': items}})


class BrandView(APIView):
    permission_classes = []
    authentication_classes = []

    @extend_schema(responses=envelope('BrandResponse', BrandSerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': {
            'name': config_value('brand.name'), 'tagline': config_value('brand.tagline'), 'logo': config_value('brand.logo'),
        }})
