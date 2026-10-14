"""公告写入、状态转换和不含正文的审计共用事务。"""
import hashlib
import json
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, NotFound, APIException
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework.generics import get_object_or_404
from apps.core.modules import module_enabled
from apps.permissions.permissions import has_permission_code
from .models import Announcement
from .announcement_content import prepare_content


class AnnouncementConflict(APIException):
    status_code = 409
    default_detail = '公告已变化，请刷新后重试'


def authorize(request, code=None, lock=False):
    if not module_enabled('notifications'):
        raise NotFound()
    query = get_user_model().objects
    if lock:
        query = query.select_for_update()
    user = query.filter(pk=request.user.pk).first()
    if not user or not user.is_active or (request.auth is not None and (
            request.auth.get('session_version') != user.session_version
            or (request.auth.get('hash_password') is not None and request.auth.get('hash_password') != get_md5_hash_password(user.password)))):
        raise AuthenticationFailed('登录凭据已撤销')
    if user.must_change_password:
        raise PermissionDenied('请先修改初始密码')
    if lock and request.auth is not None:
        from apps.auth_app.sessions import locked_request_session
        locked_request_session(request, user)
    if code and (not (user.is_staff or user.is_superuser) or not has_permission_code(user, code)):
        raise PermissionDenied('没有公告管理权限')
    return user


def audit(request, actor, row, action, before_version=None, before=None):
    # 正文可能包含内部信息；审计只记录长度/摘要和转换，不复制内容。
    from apps.logs.audit import snapshot, write_audit
    write_audit(request=request, actor=actor, action='create' if action == 'create' else 'update',
        resource='announcement', identifier=row.pk, before=before, after=snapshot('announcement', row),
        description=json.dumps({'operation': action, 'before_version': before_version, 'version': row.version,
            'status': row.status, 'content_format': row.content_format, 'content_length': len(row.content),
            'content_sha256': hashlib.sha256(row.content.encode()).hexdigest()}, ensure_ascii=False))


def create_announcement(request, actor, data):
    if data['version'] != 0:
        raise AnnouncementConflict('新建公告版本必须为 0')
    content_format = data.get('content_format', 'plain')
    content = prepare_content(data['content'], content_format)
    row = Announcement.objects.create(title=data['title'], content=content, content_format=content_format,
                                      created_by=actor, updated_by=actor)
    audit(request, actor, row, 'create')
    return row


def mutate_announcement(request, actor, pk, data, operation):
    row = get_object_or_404(Announcement.objects.select_for_update(), pk=pk)
    if row.version != data['version']:
        raise AnnouncementConflict()
    if operation == 'edit' and row.status == 'published':
        raise AnnouncementConflict('已发布公告必须先撤回才能编辑')
    if operation == 'publish' and row.status not in ('draft', 'withdrawn'):
        raise AnnouncementConflict('公告已经发布')
    if operation == 'withdraw' and row.status != 'published':
        raise AnnouncementConflict('只能撤回已发布公告')
    before = row.version
    from apps.logs.audit import snapshot
    before_values = snapshot('announcement', row)
    values = {'version': before + 1, 'updated_by': actor, 'updated_at': timezone.now()}
    if operation == 'edit':
        content_format = data.get('content_format', row.content_format)
        values.update(title=data['title'], content=prepare_content(data['content'], content_format), content_format=content_format)
    elif operation == 'publish':
        values.update(status='published', published_at=timezone.now(), content=prepare_content(row.content, row.content_format))
    else:
        # 撤回也净化持久正文，但不因遗留空正文阻止管理员停止公开。
        values.update(status='withdrawn', content=prepare_content(row.content, row.content_format, validate=False))
    # CAS also protects databases whose select_for_update is a no-op.
    if Announcement.objects.filter(pk=pk, version=before, status=row.status).update(**values) != 1:
        raise AnnouncementConflict()
    row.refresh_from_db()
    audit(request, actor, row, operation, before, before_values)
    return row
