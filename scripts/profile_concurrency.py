"""由独立 PostgreSQL 验收库注入：头像绑定与陈旧用户删除的锁顺序。"""
import io
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from types import SimpleNamespace

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections, transaction
from rest_framework_simplejwt.utils import get_md5_hash_password
from apps.auth_app.profile import replace_avatar
from apps.core.exceptions import APIError
from apps.files.models import FileModel

assert settings.DATABASES['default']['NAME'] == 'foundation', '拒绝在正式库执行'
assert connections['default'].vendor == 'postgresql'
User = get_user_model()
image = io.BytesIO()
Image.new('RGBA', (256, 256), 'blue').save(image, format='PNG')


def in_thread(call):
    try:
        return call()
    finally:
        connections.close_all()


def request_for(user):
    return SimpleNamespace(user=user, auth={'session_version': user.session_version,
        'hash_password': get_md5_hash_password(user.password)}, META={'REMOTE_ADDR': '127.0.0.1'})


owner = User.objects.create_user('profile-concurrency', password='Fixture#Secure27835')
stale = User.objects.get(pk=owner.pk)
locked, release = Event(), Event()


def upload_and_hold():
    with transaction.atomic():
        bound = replace_avatar(request_for(owner), {'profile_version': 1, 'file': image.getvalue()})
        asset_id = bound.avatar_file_id
        locked.set()
        assert release.wait(10)
    return asset_id


with ThreadPoolExecutor(max_workers=2) as pool:
    first = pool.submit(in_thread, upload_and_hold)
    assert locked.wait(10)
    second = pool.submit(in_thread, stale.delete)
    try:
        try:
            second.result(timeout=0.25)
            raise AssertionError('删除用户未等待头像绑定行锁')
        except TimeoutError:
            pass
    finally:
        release.set()
    asset_id = first.result(timeout=10)
    second.result(timeout=10)
asset = FileModel.objects.get(pk=asset_id)
assert asset.is_deleted and asset.uploader_id is None
asset.hard_delete()

owner = User.objects.create_user('profile-concurrency-deleted', password='Fixture#Secure27835')
locked, release = Event(), Event()


def delete_and_hold():
    with transaction.atomic():
        User.objects.get(pk=owner.pk).delete()
        locked.set()
        assert release.wait(10)


def competing_upload():
    try:
        replace_avatar(request_for(owner), {'profile_version': 1, 'file': image.getvalue()})
        raise AssertionError('已删除用户仍能绑定头像')
    except APIError as error:
        assert error.status_code == 401


with ThreadPoolExecutor(max_workers=2) as pool:
    first = pool.submit(in_thread, delete_and_hold)
    assert locked.wait(10)
    second = pool.submit(in_thread, competing_upload)
    try:
        try:
            second.result(timeout=0.25)
            raise AssertionError('上传未等待删除的用户行锁')
        except TimeoutError:
            pass
    finally:
        release.set()
    first.result(timeout=10)
    second.result(timeout=10)
assert not FileModel.objects.filter(uploader_id=owner.pk).exists()
print('PostgreSQL 头像绑定/陈旧删除及删除/上传竞争全部通过')
