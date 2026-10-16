from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.idempotency import with_idempotency
from apps.core.query_budget import QueryBudgetListMixin
from apps.core.schema import envelope, MessageResponse
from apps.permissions.permissions import HasPermission
from .models import FeatureFlag
from .serializers import (FeatureFlagSerializer, VersionSerializer, EvaluationRequestSerializer, EvaluationSerializer,
                          TargetQuerySerializer, TargetSerializer)
from .services import evaluate, mutate, locked_actor


class PrivateResponseMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('FeatureFlagDetailResponse', FeatureFlagSerializer())),
    create=extend_schema(responses={201: envelope('FeatureFlagCreatedResponse', FeatureFlagSerializer())}),
    partial_update=extend_schema(responses=envelope('FeatureFlagUpdatedResponse', FeatureFlagSerializer())),
    destroy=extend_schema(request=VersionSerializer, responses={200: MessageResponse}),
)
class FeatureFlagViewSet(PrivateResponseMixin, QueryBudgetListMixin, viewsets.ModelViewSet):
    serializer_class = FeatureFlagSerializer
    queryset = FeatureFlag.objects.all()
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'feature_flag:read', 'retrieve': 'feature_flag:read', 'create': 'feature_flag:create',
                      'partial_update': 'feature_flag:update', 'destroy': 'feature_flag:delete'}
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    search_fields = ['key', 'name']
    filterset_fields = ['enabled']
    ordering_fields = ['key', 'created_at', 'updated_at']
    ordering = ['key']

    def retrieve(self, request, *args, **kwargs):
        return Response({'code': 200, 'message': 'success', 'data': self.get_serializer(self.get_object()).data})

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        locked_actor(request, 'create')
        def execute():
            row = mutate(request, 'create', serializer.validated_data)
            return Response({'code': 201, 'message': '创建成功', 'data': self.get_serializer(row).data}, status=201)
        return with_idempotency(request, 'feature_flag:create', execute)

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        row = mutate(request, 'update', serializer.validated_data, self.kwargs['pk'])
        return Response({'code': 200, 'message': '更新成功', 'data': self.get_serializer(row).data})

    def destroy(self, request, *args, **kwargs):
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mutate(request, 'delete', serializer.validated_data, self.kwargs['pk'])
        return Response({'code': 200, 'message': '删除成功', 'data': None})


class EvaluateView(PrivateResponseMixin, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=EvaluationRequestSerializer,
                   responses=envelope('FeatureFlagEvaluationResponse', EvaluationSerializer(many=True)))
    def post(self, request):
        serializer = EvaluationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = evaluate(serializer.validated_data['keys'], request.user)
        return Response({'code': 200, 'message': 'success',
                         'data': [{'key': key, 'enabled': enabled} for key, enabled in data.items()]})


class TargetsView(PrivateResponseMixin, APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = 'feature_flag:read'

    @extend_schema(parameters=[TargetQuerySerializer], responses=envelope('FeatureFlagTargetsResponse', TargetSerializer(many=True)))
    def get(self, request):
        from django.contrib.auth import get_user_model
        from django.db.models import Q
        from apps.permissions.models import Role
        serializer = TargetQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        model, field = (get_user_model(), 'username') if values['kind'] == 'users' else (Role, 'name')
        base = model.objects.filter(is_active=True)
        ids = list(base.filter(**{field + '__icontains': values['search']}).order_by(field).values_list('pk', flat=True)[:50])
        rows = model.objects.filter(Q(pk__in=ids) | Q(pk__in=values['selected'])).order_by(field)
        return Response({'code': 200, 'message': 'success', 'data': [
            {'id': str(row.pk), 'label': getattr(row, field) + ('' if row.is_active else ' (disabled)')} for row in rows]})
