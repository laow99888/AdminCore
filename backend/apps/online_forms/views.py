from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.auth_app.write_authorization import authorize_write
from apps.core.idempotency import with_idempotency
from apps.core.mixins import EnvelopeResponseMixin
from apps.permissions.permissions import HasPermission
from .models import OnlineForm, OnlineFormRecord
from .serializers import OnlineFormDesignSerializer, OnlineFormRecordSerializer, OnlineFormSerializer
from .validators import validate_record


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
        serializer.save(created_by=actor)

    @transaction.atomic
    def perform_update(self, serializer):
        row = self.get_object()
        if row.status != 'draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('已发布或归档表单不可直接修改')
        authorize_write(self.request, 'online_form:update', admin=True)
        serializer.save(version=row.version + 1)

    @extend_schema(responses=OnlineFormSerializer)
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission], url_path='publish')
    @transaction.atomic
    def publish(self, request, pk=None):
        row = self.get_object()
        authorize_write(request, 'online_form:publish', admin=True)
        if row.status != 'draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('只有草稿可以发布')
        row.status, row.published_by, row.published_at = 'published', request.user, timezone.now()
        row.save(update_fields=['status', 'published_by', 'published_at', 'updated_at'])
        return Response({'code': 200, 'message': '表单已发布', 'data': OnlineFormSerializer(row).data})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission], url_path='archive')
    @transaction.atomic
    def archive(self, request, pk=None):
        row = self.get_object()
        authorize_write(request, 'online_form:update', admin=True)
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
    permission_classes = [IsAuthenticated]
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

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        form = OnlineForm.objects.filter(code=kwargs['code'], status='published').first()
        if form is None:
            from rest_framework.exceptions import NotFound
            raise NotFound('表单不存在或未发布')
        authorize_write(request, 'online_form:record_create')
        data = validate_record(form.definition, request.data.get('data', request.data))
        def execute():
            row = OnlineFormRecord.objects.create(form=form, form_version=form.version, owner=request.user, data=data)
            return Response({'code': 201, 'message': '提交成功', 'data': OnlineFormRecordSerializer(row).data}, status=201)
        return with_idempotency(request, 'online_form:record_create', execute)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        row = self.get_object()
        authorize_write(request, 'online_form:record_update')
        expected = request.data.get('version')
        if expected != row.version:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'version': '记录已变化，请刷新后重试'})
        row.data = validate_record(row.form.definition, request.data.get('data', request.data))
        row.version += 1
        row.save(update_fields=['data', 'version', 'updated_at'])
        return Response({'code': 200, 'message': '保存成功', 'data': OnlineFormRecordSerializer(row).data})
