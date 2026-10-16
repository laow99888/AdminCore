"""由 validate_foundation 注入 Django shell；只允许其独立 PostgreSQL 验收库。"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from threading import Barrier, Event

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections, transaction
from django.utils import timezone

from apps.core.models import LifecycleConflict
from apps.files.models import FileModel

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行并发验收'
assert connections['default'].vendor == 'postgresql'
owner = get_user_model().objects.get(username='admin')
cutoff = timezone.now() - timedelta(days=30)


def fixture():
    row = FileModel.objects.create(original_name='concurrency-fixture.txt', uploader=owner,
                                   file_type='txt', size=7,
                                   file=SimpleUploadedFile('concurrency-fixture.txt', b'fixture'))
    row.soft_delete(actor=owner)
    FileModel.objects.filter(pk=row.pk).update(deleted_at=cutoff - timedelta(days=1))
    return row


def in_thread(call):
    try:
        return call()
    finally:
        connections.close_all()


# 恢复事务持锁未提交时，清理必须等待；提交后复核 active 状态并跳过。
row = fixture()
locked, release = Event(), Event()


def restore_and_hold():
    with transaction.atomic():
        fresh = FileModel.objects.get(pk=row.pk)
        fresh.restore(2)
        locked.set()
        assert release.wait(10)


with ThreadPoolExecutor(max_workers=2) as pool:
    first = pool.submit(in_thread, restore_and_hold)
    assert locked.wait(10)
    second = pool.submit(in_thread, lambda: row.hard_delete(deleted_before=cutoff))
    try:
        try:
            second.result(timeout=0.25)
            raise AssertionError('清理未等待恢复的数据库行锁')
        except TimeoutError:
            pass
    finally:
        release.set()
    first.result(timeout=10)
    assert second.result(timeout=10) is False
row.refresh_from_db()
assert not row.is_deleted and row.file.storage.exists(row.file.name)
row.hard_delete()


# 两个请求同一版本的恢复，数据库只允许一个成功。
row = fixture()
barrier = Barrier(2)


def competing_restore():
    fresh = FileModel.objects.get(pk=row.pk)
    barrier.wait(timeout=10)
    try:
        fresh.restore(2)
        return 'restored'
    except LifecycleConflict:
        return 'conflict'


with ThreadPoolExecutor(max_workers=2) as pool:
    outcomes = list(pool.map(lambda _: in_thread(competing_restore), range(2)))
assert sorted(outcomes) == ['conflict', 'restored']
row.hard_delete()


# 同时竞争恢复/清理：最终要么完整恢复，要么完整清理，不能出现 active 但文件缺失。
for attempt in range(8):
    row = fixture()
    barrier = Barrier(2)
    key, storage, pk = row.file.name, row.file.storage, row.pk

    def recover():
        barrier.wait(timeout=10)
        try:
            row.restore(2)
            return 'restored'
        except FileModel.DoesNotExist:
            return 'purged'

    def clean():
        other = FileModel.objects.get(pk=pk)
        barrier.wait(timeout=10)
        return other.hard_delete(deleted_before=cutoff)

    with ThreadPoolExecutor(max_workers=2) as pool:
        recovery = pool.submit(in_thread, recover)
        cleanup = pool.submit(in_thread, clean)
        state, removed = recovery.result(timeout=10), cleanup.result(timeout=10)
    survivor = FileModel.objects.filter(pk=pk).first()
    if survivor:
        assert state == 'restored' and not removed and not survivor.is_deleted and storage.exists(key)
        survivor.hard_delete()
    else:
        from apps.core.tasks import dispatch_outbox
        assert storage.exists(key)  # 事务提交只登记删除意图。
        dispatch_outbox()
        assert state == 'purged' and removed and not storage.exists(key)
print('回收站 PostgreSQL 行锁、双恢复版本冲突、8 次恢复/清理竞争全部通过')
