"""备份只在这里登记/领取；宿主机负责停写与实际 I/O。"""
from datetime import datetime, timedelta
import re
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.modules import task_enabled
from .models import BackupRequest, BackupRestoreRequest, BackupRunnerStatus, TaskRecord

FAILURE_CODES = {'backup_failed', 'service_resume_failed', 'runner_lost', 'result_unknown'}


def policy():
    return {'retention_days': settings.ADMINCORE_BACKUP_RETENTION_DAYS,
            'retention_count': settings.ADMINCORE_BACKUP_RETENTION_COUNT}


def available():
    return settings.ADMINCORE_BACKUP_ENABLED and task_enabled('tasks.request_backup')


def register(record=None, dry_run=False, celery_task_id=''):
    if type(dry_run) is not bool:
        raise ValueError('invalid_options')
    if dry_run:
        record = record or TaskRecord.objects.create(name='备份策略预览', task_type='backup',
            status='running', related_resource='backup:preview', started_at=timezone.now())
        result = {**policy(), 'dry_run': True, 'requires_host_runner': True, 'enabled': available(),
                  'consistency': 'stop_writers'}
        record.mark_success(result)
        return result
    recover_lost()
    if not available():
        if record:
            record.mark_failed('backup_disabled')
        return {'skipped': True, 'reason': 'backup_disabled'}
    try:
        with transaction.atomic():
            record = record or TaskRecord.objects.create(name='数据库与媒体备份', task_type='backup',
                celery_task_id=celery_task_id, related_resource='maintenance:backup')
            BackupRequest.objects.get_or_create(record=record, defaults={'options': policy()})
    except IntegrityError:
        return {'skipped': True, 'reason': 'already_pending'}
    return {'queued': True, 'record_id': str(record.pk)}


def fail_record(record, code):
    record.mark_failed(code)
    from apps.notifications.models import Notification
    recipients = list(get_user_model().objects.filter(is_active=True).filter(
        Q(is_staff=True) | Q(is_superuser=True)).values_list('pk', flat=True))
    Notification.push(recipients, '自动备份失败',
        content='备份未完成，请检查宿主执行器日志及服务状态。错误代码：' + code,
        notification_type='task', link='/tasks', data={'record_id': str(record.pk), 'code': code},
        dedupe_key='backup-failed:' + str(record.pk))


def recover_lost():
    cutoff = timezone.now() - timedelta(hours=2)
    with transaction.atomic():
        pending = TaskRecord.objects.select_for_update().filter(related_resource='maintenance:backup', status='pending')
        if available():
            pending = pending.filter(created_at__lt=cutoff)
        for record in pending:
            fail_record(record, 'runner_unavailable' if available() else 'backup_disabled')
        for record in TaskRecord.objects.select_for_update(of=('self',)).filter(
            backup_request__claimed_at__lt=cutoff, status='running'):
            fail_record(record, 'result_unknown')


def claim():
    recover_lost()
    if not available():
        return None
    with transaction.atomic():
        record = TaskRecord.objects.select_for_update(of=('self',)).filter(
            related_resource='maintenance:backup', status='pending',
            backup_request__claim_token__isnull=True, backup_request__isnull=False).order_by('created_at').first()
        if not record:
            return None
        request = BackupRequest.objects.select_for_update().get(pk=record.pk)
        if record.status != 'pending':
            return None
        options = request.options
        if (not isinstance(options, dict) or set(options) != {'retention_days', 'retention_count'}
                or type(options['retention_days']) is not int or not 1 <= options['retention_days'] <= 3650
                or type(options['retention_count']) is not int or not 1 <= options['retention_count'] <= 1000):
            fail_record(record, 'backup_failed')
            return None
        manual = getattr(record, 'maintenance_request', None)
        if manual:
            from apps.permissions.permissions import has_permission_code
            user = record.creator
            if (not user or not user.is_active or user.must_change_password
                    or not (user.is_staff or user.is_superuser)
                    or user.session_version != manual.session_version
                    or not has_permission_code(user, 'schedule:run')
                    or record.created_at < timezone.now() - timedelta(hours=24)):
                fail_record(record, 'execution_not_authorized')
                return None
        request.claim_token, request.claimed_at = uuid.uuid4(), timezone.now()
        request.save(update_fields=['claim_token', 'claimed_at'])
        record.mark_started()
        return {'record_id': str(record.pk), 'token': str(request.claim_token), **options}


def validate_result(result):
    fields = {'timestamp', 'artifacts', 'remote_copy', 'pruned_sets', 'retention_warning'}
    if not isinstance(result, dict) or set(result) != fields:
        raise ValueError('invalid_result')
    stamp = result['timestamp']
    if not isinstance(stamp, str) or not re.fullmatch(r'\d{8}-\d{6}', stamp):
        raise ValueError('invalid_result')
    try:
        datetime.strptime(stamp, '%Y%m%d-%H%M%S')
    except ValueError:
        raise ValueError('invalid_result') from None
    expected = {f'admincore-db-{stamp}.dump', f'admincore-media-{stamp}.tar.gz', f'admincore-{stamp}.sha256'}
    artifacts = result['artifacts']
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise ValueError('invalid_result')
    names = set()
    for item in artifacts:
        if (not isinstance(item, dict) or set(item) != {'name', 'sha256', 'bytes'}
                or not isinstance(item['name'], str) or item['name'] not in expected
                or not isinstance(item['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', item['sha256'])
                or type(item['bytes']) is not int or not 0 < item['bytes'] <= 2**63 - 1):
            raise ValueError('invalid_result')
        names.add(item['name'])
    if (names != expected or type(result['remote_copy']) is not bool
            or type(result['retention_warning']) is not bool or type(result['pruned_sets']) is not int
            or not 0 <= result['pruned_sets'] <= 1000000):
        raise ValueError('invalid_result')
    return result


def complete(record_id, token, result=None, code=None):
    if code is None:
        result = validate_result(result)
    elif code not in FAILURE_CODES:
        raise ValueError('invalid_failure_code')
    with transaction.atomic():
        record = TaskRecord.objects.select_for_update().filter(pk=record_id, related_resource='maintenance:backup').first()
        request = BackupRequest.objects.select_for_update().filter(
            pk=record_id, claim_token=token).first()
        if not record or not request or record.status != 'running':
            raise ValueError('claim_not_running')
        # 与取消接口保持同一行锁；运行中备份从不伪装取消。
        if code:
            fail_record(record, code)
        else:
            record.mark_success(result)


def runner_heartbeat(payload):
    fields = {'state', 'directory_label', 'stage', 'last_error', 'artifacts'}
    if not isinstance(payload, dict) or set(payload) not in (fields, fields | {'restore_receipts'}):
        raise ValueError('invalid_status')
    if (payload['state'] not in {'idle', 'running', 'error'}
            or not all(isinstance(payload[k], str) and len(payload[k]) <= limit
                       for k, limit in [('directory_label', 200), ('stage', 40), ('last_error', 200)])):
        raise ValueError('invalid_status')
    artifacts = payload['artifacts']
    if not isinstance(artifacts, list) or len(artifacts) > 100:
        raise ValueError('invalid_status')
    for row in artifacts:
        if (not isinstance(row, dict) or set(row) != {'timestamp', 'created_at', 'artifacts', 'remote_copy'}
                or not isinstance(row['timestamp'], str) or not re.fullmatch(r'\d{8}-\d{6}', row['timestamp'])
                or not isinstance(row['created_at'], str) or type(row['remote_copy']) is not bool
                or not isinstance(row['artifacts'], list) or len(row['artifacts']) != 3):
            raise ValueError('invalid_status')
        validate_result({'timestamp': row['timestamp'], 'artifacts': row['artifacts'],
                         'remote_copy': row['remote_copy'], 'pruned_sets': 0, 'retention_warning': False})
        try:
            created = datetime.fromisoformat(row['created_at'])
            if created.tzinfo is None:
                raise ValueError('invalid_status')
        except ValueError:
            raise ValueError('invalid_status') from None
    row, _ = BackupRunnerStatus.objects.get_or_create(pk=1)
    row.state, row.directory_label, row.stage, row.last_error = (payload[k] for k in ('state', 'directory_label', 'stage', 'last_error'))
    row.artifacts = artifacts
    receipts = payload.get('restore_receipts', [])
    if not isinstance(receipts, list) or len(receipts) > 20:
        raise ValueError('invalid_status')
    for receipt in receipts:
        if (not isinstance(receipt, dict) or set(receipt) != {'id', 'timestamp', 'status', 'error', 'created_at', 'completed_at'}
                or any(not isinstance(value, str) for value in receipt.values())
                or receipt['status'] not in {'succeeded', 'failed', 'unknown'}
                or not re.fullmatch(r'\d{8}-\d{6}', receipt['timestamp'])
                or len(receipt['error']) > 200 or len(receipt['created_at']) > 50 or len(receipt['completed_at']) > 50):
            raise ValueError('invalid_status')
        uuid.UUID(receipt['id'])
    row.restore_receipts = receipts
    row.last_seen_at = timezone.now()
    row.save()
    # 宿主回执不随应用数据库回退；将恢复后重新出现的旧请求收敛为终态。
    for receipt in receipts:
        BackupRestoreRequest.objects.filter(pk=receipt['id'], status__in=['pending', 'running']).update(
            status=receipt['status'], error=receipt['error'], completed_at=timezone.now(), updated_at=timezone.now())
    BackupRestoreRequest.objects.filter(status='running', updated_at__lt=timezone.now() - timedelta(hours=2)).update(
        status='unknown', error='runner_lost', completed_at=timezone.now(), updated_at=timezone.now())
    return {'updated': True}


def claim_restore():
    if not available():
        return None
    with transaction.atomic():
        row = BackupRestoreRequest.objects.select_for_update().filter(status='pending').order_by('created_at').first()
        if not row:
            return None
        from apps.permissions.permissions import has_permission_code
        actor = row.requested_by
        from .reliability import valid_execution
        catalog = BackupRunnerStatus.objects.filter(pk=1).first()
        item = next((item for item in (catalog.artifacts if catalog else [])
                     if item.get('timestamp') == row.timestamp), None)
        import hashlib
        import json
        if (not valid_execution(row, actor)
                or not (actor.is_staff or actor.is_superuser)
                or actor.session_version != row.session_version
                or not has_permission_code(actor, 'backup:restore')
                or row.created_at < timezone.now() - timedelta(minutes=15)
                or item is None
                or hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest() != row.artifact_digest):
            row.status, row.error, row.completed_at = 'failed', 'execution_not_authorized', timezone.now()
            row.save(update_fields=['status', 'error', 'completed_at', 'updated_at'])
            return None
        row.status = 'running'
        row.save(update_fields=['status', 'updated_at'])
        return {'request_id': str(row.pk), 'timestamp': row.timestamp, 'artifact_digest': row.artifact_digest}


def finish_restore(request_id, status='unknown', error=''):
    if (not isinstance(status, str) or status not in {'succeeded', 'failed', 'unknown'}
            or not isinstance(error, str) or len(error) > 200):
        raise ValueError('invalid_restore_result')
    row = BackupRestoreRequest.objects.filter(pk=request_id, status='running').first()
    if not row:
        raise ValueError('restore_claim_not_running')
    row.status, row.error, row.completed_at = status, error, timezone.now()
    row.save(update_fields=['status', 'error', 'completed_at', 'updated_at'])
    return {'updated': True}
