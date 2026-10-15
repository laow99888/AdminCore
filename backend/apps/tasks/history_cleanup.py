"""显式预览后分批删除任务历史；从不作为自动保留策略执行。"""
from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.auth_app.write_authorization import authorize_write
from apps.core.data_scope import scope_queryset
from apps.core.system_views import VersionConflict
from apps.logs.audit import snapshot, write_audit
from .models import TaskRecord

SALT = 'admincore.task-history-cleanup.v1'


def signature_rows(rows):
    return [[str(row.pk), row.status, row.updated_at.isoformat()] for row in rows]


@transaction.atomic
def clean(request, values):
    actor = authorize_write(request, 'task:delete')
    days, batch_size = values['days'], values['batch_size']
    identity = {'actor': str(actor.pk), 'session': str(request.auth.get('sid', '')) if request.auth is not None else '',
                'session_version': actor.session_version, 'days': days, 'batch_size': batch_size}
    query = scope_queryset(TaskRecord.objects.all(), actor, 'task', 'creator_id').filter(
        status__in=['success', 'failed', 'cancelled'], created_at__lt=timezone.now()-timedelta(days=days))
    # Backup history owns artifact/retention metadata and is retained by the backup service.
    protected = query.filter(task_type='backup').count()
    query = query.exclude(task_type='backup')
    if values['dry_run']:
        total = query.count()
        rows = list(query.order_by('created_at', 'pk')[:batch_size])
        token = signing.dumps({**identity, 'rows': signature_rows(rows)}, salt=SALT, compress=True)
        return {'dry_run': True, 'eligible': total, 'selected': len(rows), 'deleted': 0,
                'ids': [str(row.pk) for row in rows], 'more': total > len(rows),
                'protected_backup_records': protected, 'preview_token': token, 'expires_in': 900}
    if values.get('confirmation') != '执行清理' or not values.get('preview_token'):
        raise ValidationError('执行前需要 15 分钟内的有效预览与确认；策略变化后需重新预览')
    try:
        planned = signing.loads(values['preview_token'], salt=SALT, max_age=900)
        if not isinstance(planned, dict) or {key: planned.get(key) for key in identity} != identity:
            raise ValueError()
        expected = planned['rows']
        if (not isinstance(expected, list) or len(expected) > batch_size
                or any(not isinstance(row, list) or len(row) != 3 for row in expected)):
            raise ValueError()
        identifiers = [row[0] for row in expected]
        rows = list(query.select_for_update().filter(pk__in=identifiers).order_by('created_at', 'pk'))
        if signature_rows(rows) != expected:
            raise ValueError()
    except (signing.BadSignature, ValueError, TypeError, KeyError):
        raise VersionConflict() from None
    for row in rows:
        write_audit(request=request, resource='task', identifier=row.pk, action='delete',
                    before=snapshot('task', row), description='显式预览确认后清理任务历史')
    TaskRecord.objects.filter(pk__in=identifiers).delete()
    return {'dry_run': False, 'selected': len(rows), 'deleted': len(rows),
            'more': query.exists(), 'protected_backup_records': protected}
