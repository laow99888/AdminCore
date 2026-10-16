from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.client_ip import request_ip
from apps.permissions.permissions import HasPermission
from .serializers import IPPolicySerializer, PolicyPreviewSerializer, IPPolicyPreviewResultSerializer
from .services import current_policy, update_policy, permits
from apps.core.schema import envelope


class PolicyView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'get': 'ip_policy:read', 'put': 'ip_policy:update'}

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response

    @extend_schema(responses=envelope('IPPolicyDetail', IPPolicySerializer()))
    def get(self, request):
        return Response({'code': 200, 'message': 'success', 'data': IPPolicySerializer(current_policy()).data})

    @extend_schema(request=IPPolicySerializer, responses=envelope('IPPolicyUpdated', IPPolicySerializer()))
    def put(self, request):
        serializer = IPPolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = update_policy(request, serializer.validated_data)
        return Response({'code': 200, 'message': '更新成功', 'data': IPPolicySerializer(row).data})


class PreviewView(PolicyView):
    permission_map = {'post': 'ip_policy:read'}
    http_method_names = ['post', 'options']

    @extend_schema(request=PolicyPreviewSerializer, responses=envelope('IPPolicyPreview', IPPolicyPreviewResultSerializer()))
    def post(self, request):
        serializer = PolicyPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = request_ip(request)
        return Response({'code': 200, 'message': 'success', 'data': {
            'source_ip': source, 'allowed': permits(serializer.validated_data, source)}})
