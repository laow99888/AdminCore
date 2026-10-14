"""仅在隔离 foundation PostgreSQL 运行：真实行锁、接续及失败投递。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
import secrets
from threading import Barrier
import time
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth_app.sessions import issue_session
from apps.core.models import OutboxEvent, SystemConfig
from apps.data_io.tasks import run_data_import
from apps.data_io.resources import get_resource
from apps.tasks.models import TaskRecord, ImportRowReceipt, ImportBatch
from apps.tasks.reliability import recover_lost_imports, deliver_failure
from apps.notifications.models import Notification

assert settings.DATABASES['default']['NAME'] == 'foundation', '禁止在正式库运行'
assert connections['default'].vendor == 'postgresql'
User = get_user_model()
actor = User.objects.create_superuser('task-concurrency-fixture', password=secrets.token_urlsafe(40))
token = issue_session(actor)
checks = []


def check(label, value):
    assert value, label
    checks.append(label)
    print('通过：任务可靠性 ' + label, flush=True)


def client():
    value = APIClient(HTTP_HOST='backend')
    value.credentials(HTTP_AUTHORIZATION='Bearer ' + str(token.access_token))
    return value


def submit(prefix):
    source = io.BytesIO(('username,email\n' + prefix + '1,a@example.com\n' + prefix + '2,b@example.com\n').encode())
    source.name = 'tasks.csv'
    response = client().post('/api/v1/data-io/import/', {'file': source, 'resource': 'users'}, format='multipart')
    check('源文件和执行可靠登记', response.status_code == 200)
    return TaskRecord.objects.get(pk=response.json()['data']['id'])


def parallel(function, count=2):
    barrier = Barrier(count)
    def run(index):
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            return function(index)
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(run, range(count)))


# 提交后的触发仅延迟到真实 worker HTTP 验收阶段；这里核对 SQL 竞争。
with patch('apps.core.events._dispatch_after_commit'):
    record = submit('task_once_')
    parallel(lambda _: run_data_import(str(record.pk)))
    record.refresh_from_db()
    check('两个线程重复投递仅一执行/两行提交', record.status == 'success'
          and User.objects.filter(username__startswith='task_once_').count() == 2
          and ImportRowReceipt.objects.filter(batch=record.import_execution.batch).count() == 2)

    interrupted = submit('task_resume_')
    config = get_resource('users')
    original = config['create_row']
    def interrupt(data):
        result = original(data)
        if data['username'].endswith('2'):
            raise RuntimeError('fixture simulated process failure')
        return result
    with patch.dict(config, create_row=interrupt):
        try:
            run_data_import(str(interrupted.pk))
        except RuntimeError:
            pass
    interrupted.refresh_from_db()
    check('第二行异常事务回滚，首行及账本一起保留', interrupted.status == 'failed'
          and User.objects.filter(username='task_resume_1').exists()
          and not User.objects.filter(username='task_resume_2').exists()
          and ImportRowReceipt.objects.filter(batch=interrupted.import_execution.batch).count() == 1)
    responses = parallel(lambda _: client().post(f'/api/v1/tasks/{interrupted.pk}/resume/'))
    check('同批次并发人工接续只登记一次', sorted(response.status_code for response in responses) == [202, 409])
    new = next(response.json()['data']['id'] for response in responses if response.status_code == 202)
    parallel(lambda _: run_data_import(new))
    result = TaskRecord.objects.get(pk=new)
    check('接续跳过已提交行，仍只有两个用户和账本', result.status == 'success' and result.result['created'] == 2
          and User.objects.filter(username__startswith='task_resume_').count() == 2)

    cancel = submit('task_cancel_')
    def create_then_cancel(data):
        created = original(data)
        TaskRecord.objects.filter(pk=cancel.pk).update(status='cancelled', completed_at=timezone.now())
        return created
    with patch.dict(config, create_row=create_then_cancel):
        run_data_import(str(cancel.pk))
    check('提交取消后后续行不写，已完成行不回滚', User.objects.filter(username='task_cancel_1').exists()
          and not User.objects.filter(username='task_cancel_2').exists())
    lost = submit('task_lost_')
    TaskRecord.objects.filter(pk=lost.pk).update(status='running', started_at=timezone.now() - timedelta(hours=1))
    recover_lost_imports()
    lost.refresh_from_db()
    check('失联标记失败但不自动重放', lost.error == 'worker_lost_committed_rows_preserved'
          and not User.objects.filter(username__startswith='task_lost_').exists())
    event = OutboxEvent.objects.get(topic='task.failed', payload__record_id=str(lost.pk))
    parallel(lambda _: deliver_failure(event.payload))
    check('两个消费线程失败告警去重', Notification.objects.filter(recipient=actor, data__record_id=str(lost.pk)).count() == 1)
    check('失败事件只包含安全关联编号', event.payload == {'record_id': str(lost.pk)})

    # 真正的撤权先提交：执行/投递须等待同一用户行锁，再读取新状态。
    from apps.tasks.models import MaintenanceRequest
    from apps.tasks.tasks import run_maintenance
    maintenance = TaskRecord.objects.create(name='撤权维护夹具', task_type='cleanup', creator=actor,
                                           related_resource='maintenance:notifications')
    MaintenanceRequest.objects.create(record=maintenance, key='notifications', options={'dry_run': True},
                                      session_version=actor.session_version)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            locked = User.objects.select_for_update().get(pk=actor.pk)
            executing = pool.submit(parallel, lambda _: run_maintenance(str(maintenance.pk)), 1)
            time.sleep(0.2)
            check('维护执行等待撤权用户锁', not executing.done())
            locked.session_version += 1
            locked.save(update_fields=['session_version'])
        check('撤销先提交后维护拒绝执行', executing.result(timeout=15)[0] == {'rejected': True})
    private = TaskRecord.objects.create(name='告警撤权夹具', creator=actor)
    private.mark_failed('fixture')
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            locked = User.objects.select_for_update().get(pk=actor.pk)
            sending = pool.submit(parallel, lambda _: deliver_failure({'record_id': str(private.pk)}), 1)
            time.sleep(0.2)
            if sending.done():
                sending.result()  # 若线程提前失败，保留真实异常而不是掩盖为时序断言。
            check('失败告警等待收件身份锁', not sending.done())
            locked.is_active = False
            locked.save(update_fields=['is_active'])
        sending.result(timeout=15)
    check('停用先提交后告警不投递该身份', not Notification.objects.filter(recipient=actor, data__record_id=str(private.pk)).exists())

print('任务可靠性 PostgreSQL 通过：' + str(len(checks)) + ' 项', flush=True)
