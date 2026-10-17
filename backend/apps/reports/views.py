from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.auth_app.write_authorization import authorize_write
from apps.core.mixins import EnvelopeResponseMixin
from apps.permissions.permissions import HasPermission
from .models import ReportDefinition
from .serializers import ReportDesignSerializer, ReportSerializer
from .services import catalog_for, execute_definition
from apps.core.exceptions import APIError
from rest_framework.generics import get_object_or_404


class ReportViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    queryset = ReportDefinition.objects.select_related('created_by', 'published_by').all()
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'report:read', 'retrieve': 'report:read', 'create': 'report:create', 'update': 'report:update', 'partial_update': 'report:update', 'publish': 'report:publish', 'archive': 'report:update', 'run': 'report:execute'}
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code', 'created_at', 'updated_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset if self.request.user.is_staff or self.request.user.is_superuser else queryset.filter(status__in=['published', 'archived'])

    def get_serializer_class(self):
        return ReportDesignSerializer if self.action in {'create', 'update', 'partial_update'} else ReportSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        actor = authorize_write(self.request, 'report:create', admin=True)
        serializer.save(created_by=actor, version=1)

    @transaction.atomic
    def perform_update(self, serializer):
        authorize_write(self.request, 'report:update', admin=True)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=self.kwargs['pk'])
        if row.status != 'draft':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('已发布报表不可直接修改，请复制为新草稿')
        if serializer.validated_data.pop('version', None) != row.version:
            raise APIError('报表已变化，请刷新后重试', status_code=409)
        serializer.instance = row
        serializer.save(version=row.version + 1)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def publish(self, request, *args, **kwargs):
        actor = authorize_write(request, 'report:publish', admin=True)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=kwargs['pk'])
        if 'version' in request.data and request.data['version'] != row.version:
            raise APIError('报表已变化，请刷新后重试', status_code=409)
        if row.status != 'draft':
            return Response({'code': 409, 'message': '只有草稿可以发布', 'data': None}, status=status.HTTP_409_CONFLICT)
        row.status = 'published'; row.published_by = actor; row.published_at = timezone.now(); row.save(update_fields=['status', 'published_by', 'published_at', 'updated_at'])
        return Response({'code': 200, 'message': '发布成功', 'data': ReportSerializer(row).data})

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def archive(self, request, *args, **kwargs):
        self.get_object()
        authorize_write(request, 'report:update', admin=True)
        row = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=kwargs['pk'])
        row.status = 'archived'; row.save(update_fields=['status', 'updated_at'])
        return Response({'code': 200, 'message': '归档成功', 'data': ReportSerializer(row).data})

    @action(detail=True, methods=['get'])
    def run(self, request, *args, **kwargs):
        row = self.get_object()
        if row.status != 'published':
            return Response({'code': 409, 'message': '只有已发布报表可以运行', 'data': None}, status=status.HTTP_409_CONFLICT)
        try:
            data = execute_definition(request.user, row.definition)
        except PermissionError as exc:
            return Response({'code': 403, 'message': str(exc), 'data': None}, status=status.HTTP_403_FORBIDDEN)
        return Response({'code': 200, 'message': 'success', 'data': data})


class ReportCatalogView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'report:read'

    @extend_schema(responses=dict)
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': catalog_for(request.user)})
