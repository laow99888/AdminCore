from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle
from apps.auth_app.write_authorization import authorize_write
from apps.core.idempotency import with_idempotency
from apps.core.mixins import EnvelopeResponseMixin
from apps.permissions.permissions import HasPermission, IsAdmin
from apps.core.exceptions import APIError
from rest_framework.generics import get_object_or_404
from .models import OnlineForm, OnlineFormRecord
from .serializers import OnlineFormDesignSerializer, OnlineFormRecordSerializer, OnlineFormSerializer
from .validators import validate_definition, validate_record


class FormValidationRequest(serializers.Serializer):
    definition = serializers.JSONField()
    data = serializers.JSONField(required=False)


class FormRecordCreateRequest(serializers.Serializer):
    data = serializers.JSONField()


class FormRecordUpdateRequest(FormRecordCreateRequest):
    version = serializers.IntegerField(min_value=1)


class FormValidationThrottle(UserRateThrottle):
    scope = 'online_form_validation'
    rate = '60/min'


class FormValidationView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'online_form:read'
    throttle_classes = [FormValidationThrottle]

    @extend_schema(request=FormValidationRequest, responses=FormValidationRequest)
    def post(self, request):
        serializer = FormValidationRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        definition = validate_definition(serializer.validated_data['definition'])
        result = {'definition': definition}
        if 'data' in serializer.validated_data:
            result['data'] = validate_record(definition, serializer.validated_data['data'])
        response = Response({'code': 200, 'message': 'success', 'data': result})
        response['Cache-Control'] = 'private, no-store'
        return response


class OnlineFormViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    queryset = OnlineForm.objects.select_related('created_by', 'published_by').all()
    serializer_class = OnlineFormSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'online_form:read', 'retrieve': 'online_form:read', 'create': 'online_form:create', 'update': 'online_form:update', 'partial_update': 'online_form:update', 'publish': 'online_form:publish', 'archive': 'online_form:update'}
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code', 'created_at', 'updated_at']
    ordering = ['-updated_at']

    def get_serializer_class(self):
        return OnlineFormDesignSerializer if self.action in {'create', 'update', 'partial_update'} else OnlineFormSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        actor = authorize_write(self.request, 'online_form:create', admin=True)
        serializer.save(created_by=actor, version=1)

    @transaction.atomic
    def perform_update(self, serializer):
        authorize_write(self.request, 'online_form:update', admin=True)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=self.kwargs['pk'])
        if row.status != 'draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('已发布或归档表单不可直接修改')
        if serializer.validated_data.pop('version', None) != row.version:
            raise APIError('表单已变化，请刷新后重试', status_code=409)
        serializer.instance = row
        serializer.save(version=row.version + 1)

    @extend_schema(responses=OnlineFormSerializer)
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission], url_path='publish')
    @transaction.atomic
    def publish(self, request, pk=None):
        authorize_write(request, 'online_form:publish', admin=True)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        if 'version' in request.data and request.data['version'] != row.version:
            raise APIError('表单已变化，请刷新后重试', status_code=409)
        if row.status != 'draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('只有草稿可以发布')
        row.definition = validate_definition(row.definition)
        row.status, row.published_by, row.published_at = 'published', request.user, timezone.now()
        row.save(update_fields=['definition', 'status', 'published_by', 'published_at', 'updated_at'])
        return Response({'code': 200, 'message': '表单已发布', 'data': OnlineFormSerializer(row).data})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission], url_path='archive')
    @transaction.atomic
    def archive(self, request, pk=None):
        self.get_object()
        authorize_write(request, 'online_form:update', admin=True)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        row.status = 'archived'
        row.save(update_fields=['status', 'updated_at'])
        return Response({'code': 200, 'message': '表单已归档', 'data': OnlineFormSerializer(row).data})


class PublishedFormView(APIView):
    permission_classes = [IsAuthenticated]
    @extend_schema(responses=OnlineFormSerializer)
    def get(self, request, code):
        row = OnlineForm.objects.filter(code=code, status='published').first()
        if row is None:
            from rest_framework.exceptions import NotFound
            raise NotFound('表单不存在或未发布')
        return Response({'code': 200, 'message': 'success', 'data': OnlineFormSerializer(row).data})


class FormRecordViewSet(EnvelopeResponseMixin, viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    # OpenAPI 生成阶段不会提供嵌套路由参数，使用空查询集避免 schema introspection 触发 KeyError。
    queryset = OnlineFormRecord.objects.none()
    serializer_class = OnlineFormRecordSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'online_form:record_read', 'retrieve': 'online_form:record_read',
                      'create': 'online_form:record_create', 'partial_update': 'online_form:record_update'}
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        code = self.kwargs.get('code')
        if not code:
            return self.queryset
        return OnlineFormRecord.objects.filter(form__code=code, form__status='published', owner=self.request.user).select_related('form', 'owner')

    def list(self, request, *args, **kwargs):
        from apps.permissions.permissions import has_permission_code
        if not has_permission_code(request.user, 'online_form:record_read') and not request.user.is_staff:
            return Response({'code': 403, 'message': '无权查看表单记录', 'data': None}, status=403)
        return super().list(request, *args, **kwargs)

    @extend_schema(request=FormRecordCreateRequest, responses={201: OnlineFormRecordSerializer})
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        authorize_write(request, 'online_form:record_create')
        if not isinstance(request.data, dict):
            raise ValidationError('表单记录必须为 JSON 对象')
        form = OnlineForm.objects.select_for_update().filter(code=kwargs['code'], status='published').first()
        if form is None:
            from rest_framework.exceptions import NotFound
            raise NotFound('表单不存在或未发布')
        data = validate_record(form.definition, request.data.get('data', request.data))
        def execute():
            row = OnlineFormRecord.objects.create(form=form, form_version=form.version, owner=request.user, data=data)
            return Response({'code': 201, 'message': '提交成功', 'data': OnlineFormRecordSerializer(row).data}, status=201)
        return with_idempotency(request, 'online_form:record_create', execute)

    @extend_schema(request=FormRecordUpdateRequest, responses=OnlineFormRecordSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        authorize_write(request, 'online_form:record_update')
        if not isinstance(request.data, dict):
            raise ValidationError('表单记录必须为 JSON 对象')
        expected = request.data.get('version')
        if type(expected) is not int or expected < 1:
            raise ValidationError({'version': '必须提交正整数版本号'})
        get_object_or_404(OnlineForm.objects.select_for_update(), code=kwargs['code'], status='published')
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=kwargs['pk'])
        if expected != row.version:
            raise APIError('记录已变化，请刷新后重试', status_code=409)
        row.data = validate_record(row.form.definition, request.data.get('data', request.data))
        row.version += 1
        row.save(update_fields=['data', 'version', 'updated_at'])
        return Response({'code': 200, 'message': '保存成功', 'data': OnlineFormRecordSerializer(row).data})
