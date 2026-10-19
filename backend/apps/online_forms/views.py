from copy import deepcopy
from django.db import IntegrityError, transaction
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
from .serializers import OnlineFormDesignSerializer, OnlineFormRecordDetailSerializer, OnlineFormRecordSerializer, OnlineFormSerializer
from .validators import validate_definition, validate_record
from .attachments import attach_files, validate_files
from .relations import validate_relations, validate_relation_definition
from apps.core.tenancy import current_tenant_id


class FormValidationRequest(serializers.Serializer):
    definition = serializers.JSONField()
    data = serializers.JSONField(required=False)
    form_id = serializers.UUIDField(required=False)


class FormRecordCreateRequest(serializers.Serializer):
    data = serializers.JSONField()
    form_id = serializers.UUIDField(required=False)


class FormRecordUpdateRequest(FormRecordCreateRequest):
    version = serializers.IntegerField(min_value=1)


class FormVersionRequest(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class FormOptionalVersionRequest(serializers.Serializer):
    version = serializers.IntegerField(min_value=1, required=False)


class FormApprovalChoice(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    revision = serializers.IntegerField()


class FormApprovalChoicesResponse(serializers.Serializer):
    code = serializers.IntegerField()
    message = serializers.CharField()
    data = FormApprovalChoice(many=True)


class FormApprovalChoicesQuery(serializers.Serializer):
    form_id = serializers.UUIDField(required=False)


def lock_series(code):
    """首版永不删除；所有系列变更/提交按首版→版本→记录顺序加锁。"""
    return get_object_or_404(OnlineForm.objects.select_for_update(), code=code, release_number=1)


def check_version(request, row, required=False):
    if not isinstance(request.data, dict):
        raise ValidationError('表单操作必须为 JSON 对象')
    value = request.data.get('version')
    if value is None and not required:
        return
    if type(value) is not int or value < 1:
        raise ValidationError({'version': '必须提交正整数版本号'})
    if value != row.version:
        raise APIError('表单已变化，请刷新后重试', status_code=409)


class FormValidationThrottle(UserRateThrottle):
    scope = 'online_form_validation'
    rate = '60/min'


class FormApprovalChoicesView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin, HasPermission]
    required_permission = 'online_form:read'

    @extend_schema(parameters=[FormApprovalChoicesQuery], responses=FormApprovalChoicesResponse)
    def get(self, request):
        from apps.core.modules import module_enabled
        from apps.approvals.models import ApprovalFlow
        if not module_enabled('approvals'):
            return Response({'code': 200, 'message': 'success', 'data': []})
        tenant_id = current_tenant_id()
        identifier = request.query_params.get('form_id')
        if identifier:
            query = serializers.UUIDField()
            identifier = query.run_validation(identifier)
            tenant_id = get_object_or_404(OnlineForm.objects.all(), pk=identifier).tenant_id
        rows = ApprovalFlow.objects.filter(tenant_id=tenant_id, status='published').order_by('code')
        data = [{'code': row.code, 'name': row.name, 'revision': row.revision} for row in rows]
        response = Response({'code': 200, 'message': 'success', 'data': data})
        response['Cache-Control'] = 'private, no-store'
        return response


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
            form_id = serializer.validated_data.get('form_id')
            tenant_id = get_object_or_404(OnlineForm.objects.all(), pk=form_id).tenant_id if form_id else current_tenant_id()
            validate_files(definition, result['data'], request.user, tenant_id)
            validate_relations(definition, result['data'], request.user, tenant_id)
        response = Response({'code': 200, 'message': 'success', 'data': result})
        response['Cache-Control'] = 'private, no-store'
        return response


class OnlineFormViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    queryset = OnlineForm.objects.select_related('created_by', 'published_by').all()
    serializer_class = OnlineFormSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'online_form:read', 'retrieve': 'online_form:read', 'create': 'online_form:create', 'update': 'online_form:update', 'partial_update': 'online_form:update', 'publish': 'online_form:publish', 'archive': 'online_form:update', 'new_version': 'online_form:create'}
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code', 'created_at', 'updated_at']
    ordering = ['-updated_at']

    def get_serializer_class(self):
        return OnlineFormDesignSerializer if self.action in {'create', 'update', 'partial_update'} else OnlineFormSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        actor = authorize_write(self.request, 'online_form:create', admin=True)
        try:
            with transaction.atomic():
                serializer.save(created_by=actor, version=1, release_number=1)
        except IntegrityError as exc:
            raise APIError('表单编码已存在', status_code=409) from exc

    @transaction.atomic
    def perform_update(self, serializer):
        authorize_write(self.request, 'online_form:update', admin=True)
        lock_series(serializer.instance.code)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=self.kwargs['pk'])
        if row.status != 'draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('已发布或归档表单不可直接修改')
        if serializer.validated_data.pop('version', None) != row.version:
            raise APIError('表单已变化，请刷新后重试', status_code=409)
        serializer.instance = row
        serializer.save(version=row.version + 1)

    @extend_schema(request=FormOptionalVersionRequest, responses=OnlineFormSerializer)
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission], url_path='publish')
    @transaction.atomic
    def publish(self, request, pk=None):
        authorize_write(request, 'online_form:publish', admin=True)
        lock_series(self.get_object().code)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        check_version(request, row)
        if row.status != 'draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('只有草稿可以发布')
        row.definition = validate_definition(row.definition)
        validate_relation_definition(row.definition, request.user, row.tenant_id)
        from .approval_integration import freeze_flow
        row.approval_flow = freeze_flow(row)
        row.approval_flow_version = row.approval_flow.version if row.approval_flow else None
        OnlineForm.objects.filter(code=row.code, status='published').update(status='archived', updated_at=timezone.now())
        row.status, row.published_by, row.published_at = 'published', request.user, timezone.now()
        row.save(update_fields=['definition', 'approval_flow', 'approval_flow_version', 'status', 'published_by', 'published_at', 'updated_at'])
        return Response({'code': 200, 'message': '表单已发布', 'data': OnlineFormSerializer(row).data})

    @extend_schema(request=FormVersionRequest, responses={201: OnlineFormSerializer})
    @action(detail=True, methods=['post'], url_path='new-version')
    @transaction.atomic
    def new_version(self, request, pk=None):
        actor = authorize_write(request, 'online_form:create', admin=True)
        lock_series(self.get_object().code)
        source = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        check_version(request, source, required=True)
        if source.status == 'draft':
            raise ValidationError('请保存现有草稿，不可从草稿创建新版')
        if OnlineForm.objects.filter(code=source.code, status='draft').exists():
            raise APIError('该表单已有新版草稿，请打开现有草稿', status_code=409)
        latest = OnlineForm.objects.filter(code=source.code).order_by('-release_number').first()
        row = OnlineForm.objects.create(name=source.name, code=source.code, release_number=latest.release_number + 1,
                                        definition=deepcopy(source.definition), approval_flow_code=source.approval_flow_code,
                                        created_by=actor, tenant_id=source.tenant_id)
        return Response({'code': 201, 'message': '新版草稿已创建', 'data': OnlineFormSerializer(row).data}, status=201)

    @extend_schema(request=FormOptionalVersionRequest, responses=OnlineFormSerializer)
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasPermission], url_path='archive')
    @transaction.atomic
    def archive(self, request, pk=None):
        self.get_object()
        authorize_write(request, 'online_form:update', admin=True)
        lock_series(self.get_object().code)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
        check_version(request, row)
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
                      'create': 'online_form:record_create', 'partial_update': 'online_form:record_update',
                      'submit_approval': 'online_form:record_submit', 'withdraw_approval': 'online_form:record_withdraw'}
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    generated_query_parameters = ('release_number',)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        code = self.kwargs.get('code')
        if not code:
            return self.queryset
        queryset = OnlineFormRecord.objects.filter(form__code=code, owner=self.request.user).select_related('form', 'owner')
        release = self.request.query_params.get('release_number')
        if release is not None:
            if len(release) > 10 or not release.isascii() or not release.isdecimal() or not 1 <= int(release) <= 2147483647:
                raise ValidationError({'release_number': '必须提交正整数发布版本'})
            queryset = queryset.filter(form__release_number=int(release))
        return queryset

    def get_serializer_class(self):
        return OnlineFormRecordSerializer if self.action == 'list' else OnlineFormRecordDetailSerializer

    def list(self, request, *args, **kwargs):
        from apps.permissions.permissions import has_permission_code
        if not has_permission_code(request.user, 'online_form:record_read') and not request.user.is_staff:
            return Response({'code': 403, 'message': '无权查看表单记录', 'data': None}, status=403)
        return super().list(request, *args, **kwargs)

    @extend_schema(request=FormRecordCreateRequest, responses={201: OnlineFormRecordDetailSerializer})
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        authorize_write(request, 'online_form:record_create')
        if not isinstance(request.data, dict):
            raise ValidationError('表单记录必须为 JSON 对象')
        def execute():
            lock_series(kwargs['code'])
            form = get_object_or_404(OnlineForm.objects.select_for_update(), code=kwargs['code'], status='published')
            if 'form_id' in request.data and str(request.data['form_id']) != str(form.pk):
                raise APIError('表单已发布新版，请刷新后重新填写', status_code=409)
            data = validate_record(form.definition, request.data.get('data', request.data))
            from .approval_integration import validate_record_inputs
            validate_record_inputs(form, form.definition, data)
            files = validate_files(form.definition, data, request.user, form.tenant_id, lock=True)
            validate_relations(form.definition, data, request.user, form.tenant_id, lock=True)
            row = OnlineFormRecord.objects.create(form=form, form_version=form.version, owner=request.user, data=data,
                                                   definition_snapshot=deepcopy(form.definition), tenant_id=form.tenant_id)
            attach_files(row, files)
            return Response({'code': 201, 'message': '提交成功', 'data': OnlineFormRecordDetailSerializer(row).data}, status=201)
        return with_idempotency(request, 'online_form:record_create', execute)

    @extend_schema(request=FormRecordUpdateRequest, responses=OnlineFormRecordDetailSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        authorize_write(request, 'online_form:record_update')
        if not isinstance(request.data, dict):
            raise ValidationError('表单记录必须为 JSON 对象')
        expected = request.data.get('version')
        if type(expected) is not int or expected < 1:
            raise ValidationError({'version': '必须提交正整数版本号'})
        lock_series(kwargs['code'])
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=kwargs['pk'])
        if expected != row.version:
            raise APIError('记录已变化，请刷新后重试', status_code=409)
        if row.approval_status in {'pending', 'approved'}:
            raise APIError('审批中或已通过的表单记录不可修改', status_code=409)
        row.data = validate_record(row.definition_snapshot, request.data.get('data', request.data))
        from .approval_integration import validate_record_inputs
        validate_record_inputs(row.form, row.definition_snapshot, row.data)
        files = validate_files(row.definition_snapshot, row.data, request.user, row.tenant_id, lock=True)
        validate_relations(row.definition_snapshot, row.data, request.user, row.tenant_id, lock=True)
        row.version += 1
        row.save(update_fields=['data', 'version', 'updated_at'])
        attach_files(row, files)
        return Response({'code': 200, 'message': '保存成功', 'data': OnlineFormRecordDetailSerializer(row).data})

    @extend_schema(request=FormVersionRequest, responses=OnlineFormRecordDetailSerializer)
    def submit_approval(self, request, *args, **kwargs):
        from .approval_integration import record_action
        row = record_action(request, kwargs['code'], kwargs['pk'], 'submit')
        return Response({'code': 200, 'message': '审批已提交', 'data': OnlineFormRecordDetailSerializer(row).data})

    @extend_schema(request=FormVersionRequest, responses=OnlineFormRecordDetailSerializer)
    def withdraw_approval(self, request, *args, **kwargs):
        from .approval_integration import record_action
        row = record_action(request, kwargs['code'], kwargs['pk'], 'withdraw')
        return Response({'code': 200, 'message': '审批已撤回', 'data': OnlineFormRecordDetailSerializer(row).data})
