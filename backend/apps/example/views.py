from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from rest_framework.exceptions import NotFound
from apps.core.idempotency import with_idempotency
from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.core.schema import envelope, MessageResponse
from apps.core.query_budget import QueryBudgetListMixin
from apps.permissions.permissions import HasPermission
from .serializers import WorkItemSerializer, VersionSerializer
from .services import mutate, visible, locked_actor


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('ExampleDetailResponse', WorkItemSerializer())),
    create=extend_schema(responses={201: envelope('ExampleCreatedResponse', WorkItemSerializer())}),
    update=extend_schema(responses=envelope('ExampleUpdatedResponse', WorkItemSerializer())),
    partial_update=extend_schema(responses=envelope('ExamplePatchedResponse', WorkItemSerializer())),
    destroy=extend_schema(request=VersionSerializer, responses={200: MessageResponse}),
)
class WorkItemViewSet(QueryBudgetListMixin, viewsets.ModelViewSet):
    serializer_class = WorkItemSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'example:read', 'retrieve': 'example:read', 'create': 'example:create',
                      'update': 'example:update', 'partial_update': 'example:update', 'destroy': 'example:delete'}
    filterset_fields = ['status', 'priority']
    search_fields = ['title']
    ordering_fields = ['created_at', 'updated_at', 'priority']
    ordering = ['-created_at', '-id']

    def get_queryset(self):
        return visible(self.request.user)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    def retrieve(self, request, *args, **kwargs):
        return Response({'code': 200, 'message': 'success', 'data': self.get_serializer(self.get_object()).data})

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = locked_actor(request, 'create')
        def execute():
            row = mutate(request, 'create', serializer.validated_data)
            return Response({'code': 201, 'message': '创建成功', 'data': self.get_serializer(row).data}, status=201)
        response = with_idempotency(request, 'example:create', execute)
        if not visible(actor).filter(pk=response.data['data']['id']).exists():
            raise NotFound()
        return response

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        row = mutate(request, 'update', serializer.validated_data, self.kwargs['pk'])
        return Response({'code': 200, 'message': '更新成功', 'data': self.get_serializer(row).data})

    def destroy(self, request, *args, **kwargs):
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mutate(request, 'delete', serializer.validated_data, self.kwargs['pk'])
        return Response({'code': 200, 'message': '删除成功', 'data': None})
