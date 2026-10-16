"""断点续传上传接口。"""

from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.schema import MessageResponse, envelope
from apps.files.serializers import FileSerializer

from .resumable import complete_session, get_session, put_chunk, start_session


def session_payload(row):
    return {
        'id': str(row.pk), 'status': row.status, 'original_name': row.original_name,
        'total_size': row.total_size, 'chunk_size': row.chunk_size, 'total_chunks': row.total_chunks,
        'received': sorted(int(index) for index in (row.chunks or {})),
        'expires_at': row.expires_at, 'file_id': str(row.file_id) if row.file_id else None,
    }


class ResumableUploadStartView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT, 400: MessageResponse})
    def post(self, request):
        with transaction.atomic():
            row = start_session(request, name=request.data.get('name'), total_size=request.data.get('total_size'),
                                chunk_size=request.data.get('chunk_size'), content_type=request.data.get('content_type', ''),
                                expected_sha256=request.data.get('sha256', ''))
        return Response({'code': 201, 'message': '上传会话已创建', 'data': session_payload(row)}, status=201)


class ResumableUploadDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT, 410: MessageResponse})
    def get(self, request, upload_id):
        with transaction.atomic():
            from apps.auth_app.write_authorization import authorize_write
            actor = authorize_write(request, 'file:upload')
            row = get_session(actor, upload_id)
        return Response({'code': 200, 'message': 'success', 'data': session_payload(row)})


class ResumableUploadChunkView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=OpenApiTypes.BINARY, responses={200: OpenApiTypes.OBJECT, 400: MessageResponse, 409: MessageResponse, 422: MessageResponse})
    def put(self, request, upload_id, index):
        row = put_chunk(request, upload_id, index)
        return Response({'code': 200, 'message': '分片已接收', 'data': session_payload(row)})


class ResumableUploadCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: envelope('ResumableUploadCompleteResponse', FileSerializer()), 422: MessageResponse})
    def post(self, request, upload_id):
        file_obj = complete_session(request, upload_id)
        return Response({'code': 200, 'message': '上传完成', 'data': FileSerializer(file_obj, context={'request': request}).data})
