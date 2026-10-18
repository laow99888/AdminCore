"""逻辑文档的追加版本和回退。文件内容不覆盖、ACL不继承或复制。"""
from django.db import transaction
from rest_framework.exceptions import NotFound

from apps.auth_app.write_authorization import authorize_write
from apps.core.exceptions import APIError
from apps.core.tenancy import current_tenant_id, enabled
from apps.logs.audit import write_audit
from .access import file_queryset_for_actor
from .models import FileAccessGrant, FileDocument, FileModel, FileRevision

MAX_REVISIONS = 1000


def files_for(actor, access=FileAccessGrant.READ):
    return file_queryset_for_actor(FileModel.objects.filter(
        purpose='general', is_deleted=False, tenant_id=current_tenant_id() if enabled() else None), actor, access=access)


def document_for(actor, file_id, *, lock=False):
    if not files_for(actor).filter(pk=file_id).exists():
        raise NotFound('文件不存在')
    link = FileRevision.objects.filter(file_id=file_id).first()
    if link is None:
        return None
    query = FileDocument.objects.filter(pk=link.document_id)
    if lock:
        query = query.select_for_update()
    document = query.first()
    if document is None or not files_for(actor).filter(pk=document.current_file_id).exists():
        raise NotFound('文件不存在')
    return document


def history(actor, file_id, page):
    document = document_for(actor, file_id)
    if document is None:
        return {'version': 0, 'current_file': str(file_id), 'items': [], 'has_more': False}
    rows = list(document.revisions.filter(file__in=files_for(actor)).select_related('file').order_by('-number')[
        (page - 1) * 50:page * 50 + 1])
    return {'version': document.version, 'current_file': str(document.current_file_id), 'has_more': len(rows) > 50,
            'items': [{'number': row.number, 'file_id': str(row.file_id), 'original_name': row.file.original_name,
                       'size': row.file.size, 'created_at': row.created_at, 'restored_from': row.restored_from}
                      for row in rows[:50]]}


@transaction.atomic
def append_revision(request, anchor_id, values):
    actor = authorize_write(request, 'file:upload')
    from apps.permissions.permissions import has_permission_code
    from rest_framework.exceptions import PermissionDenied
    if not has_permission_code(actor, 'file:read'):
        raise PermissionDenied()
    document = document_for(actor, anchor_id, lock=True)
    expected = values['version']
    if (document.version if document else 0) != expected:
        raise APIError('文档版本已变更，请刷新后重试', status_code=409)
    if document and document.version >= MAX_REVISIONS:
        raise APIError('单份文档最多1000个修订', status_code=409)
    target_id = values.get('file_id')
    restored_from = values.get('restore_number')
    if restored_from is not None:
        if document is None:
            raise NotFound('文档版本不存在')
        previous = document.revisions.filter(number=restored_from).first()
        if previous is None:
            raise NotFound('文档版本不存在')
        target_id = previous.file_id
    current_id = document.current_file_id if document else anchor_id
    ids = {str(anchor_id), str(current_id), str(target_id)}
    # 文档→按主键文件锁；删除方只锁文件，不反向锁文档。
    rows = list(files_for(actor, FileAccessGrant.MANAGE).filter(pk__in=ids).order_by('pk').select_for_update(of=('self',)))
    if len(rows) != len(ids) or not files_for(actor, FileAccessGrant.MANAGE).filter(pk__in=ids).count() == len(ids):
        raise NotFound('文件不存在或无权管理')
    # 新建文档时文件锁后重查，跨用户同时登记同一附件只产生一份系列。
    if document is None and FileRevision.objects.filter(file_id=anchor_id).exists():
        raise APIError('文件已加入文档，请刷新后重试', status_code=409)
    memberships = FileRevision.objects.filter(file_id=target_id)
    if document:
        memberships = memberships.exclude(document=document)
    if memberships.exists():
        raise APIError('文件已属于其他文档', status_code=409)
    if str(target_id) == str(current_id):
        raise APIError('目标文件已是当前版本', status_code=409)
    tenant_id = rows[0].tenant_id
    if document is None:
        document = FileDocument.objects.create(current_file_id=anchor_id, tenant_id=tenant_id)
        FileRevision.objects.create(document=document, file_id=anchor_id, number=1, actor=actor, tenant_id=tenant_id)
    if restored_from is None and document.revisions.filter(file_id=target_id).exists():
        raise APIError('请使用回退操作选择已有文档版本', status_code=409)
    document.version += 1
    document.current_file_id = target_id
    document.save(update_fields=['current_file', 'version', 'updated_at'])
    FileRevision.objects.create(document=document, file_id=target_id, number=document.version,
                                restored_from=restored_from, actor=actor, tenant_id=tenant_id)
    write_audit(request=request, actor=actor, resource='file_document', identifier=document.pk, action='update',
                after={'id': str(document.pk), 'version': document.version, 'current_file_id': str(target_id),
                       'restored_from': restored_from})
    return history(actor, anchor_id, 1)
