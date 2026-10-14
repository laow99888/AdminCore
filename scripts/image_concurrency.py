"""只在图片隔离 PostgreSQL 中验收锁等待后的数据泄露防护。"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
import io
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import connections, transaction
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from apps.auth_app.models import AuthSession
from apps.auth_app.sessions import issue_session
from apps.core.models import DataScopeGrant
from apps.files.models import FileModel
from apps.logs.models import OperationLog
from apps.permissions.models import Permission, Role, RolePermission, UserRole

assert settings.DATABASES['default']['NAME'] == 'images_fixture'
assert connections['default'].vendor == 'postgresql'
User = get_user_model()
output = io.BytesIO(); Image.new('RGB', (24, 16), 'blue').save(output, 'PNG')
content = output.getvalue()
for boundary in ['account', 'session', 'process', 'download', 'scope', 'version', 'deleted']:
    suffix = uuid.uuid4().hex[:10]
    actor = User.objects.create_user('image-wait-' + suffix, password='Fixture#27835')
    role = Role.objects.create(name='image-wait-' + suffix)
    UserRole.objects.create(user=actor, role=role)
    for code in ['file:process', 'file:download']:
        RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
    token = issue_session(actor)
    row = FileModel.objects.create(uploader=actor, original_name='fixture.png', file_type='png', size=len(content),
                                   file=ContentFile(content, name='fixture.png'))
    locked, release = Event(), Event()
    def revoke():
        try:
            with transaction.atomic():
                current = User.objects.select_for_update().get(pk=actor.pk)
                if boundary == 'account':
                    current.is_active = False; current.save(update_fields=['is_active'])
                elif boundary == 'session':
                    AuthSession.objects.filter(pk=token['sid']).update(revoked_at=timezone.now())
                elif boundary in {'process', 'download'}:
                    RolePermission.objects.filter(role=role, permission__code='file:' + boundary).delete()
                elif boundary == 'scope':
                    DataScopeGrant.objects.create(role=role, resource='file', scope='custom')
                elif boundary == 'version':
                    FileModel.objects.filter(pk=row.pk).update(lifecycle_version=2)
                else:
                    FileModel.objects.filter(pk=row.pk).update(is_deleted=True)
                locked.set(); assert release.wait(10)
        finally: connections.close_all()
    def read():
        try:
            client = APIClient(HTTP_HOST='backend')
            # 请求认证发生在另一事务提交前，必须在 transform 的 actor 锁后再次检查。
            client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
            return client.post(f'/api/v1/files/{row.pk}/transform/', {'lifecycle_version': 1}, format='json').status_code
        finally: connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(revoke); assert locked.wait(10); second = pool.submit(read)
        try:
            try:
                second.result(timeout=0.25)
                raise AssertionError('图片请求没有等待用户行锁')
            except TimeoutError: pass
        finally: release.set()
        first.result(timeout=10)
        assert second.result(timeout=10) == {'account': 401, 'session': 401, 'process': 403,
            'download': 403, 'scope': 404, 'version': 409, 'deleted': 404}[boundary]
    assert not OperationLog.objects.filter(resource='file_transform', resource_id=str(row.pk)).exists()
    with row.file.open('rb') as source: assert source.read() == content
print('图片处理七项 PostgreSQL 锁等待复核通过')
