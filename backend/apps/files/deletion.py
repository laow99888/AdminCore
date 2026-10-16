"""数据库提交后的幂等对象清理；可靠意图由 Outbox 保存至执行成功。"""
import hashlib
import json

from django.conf import settings
from django.core.files.storage import default_storage


def storage_identity():
    # 绑定目标库/目录，不绑定可轮换凭据；切换存储后禁止误删同名对象。
    value = {'backend': settings.STORAGES['default']['BACKEND']}
    for key in ('location', 'bucket_name', 'endpoint_url'):
        value[key] = str(getattr(default_storage, key, ''))
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def purge_object(payload):
    from .models import FileModel
    if set(payload) != {'name', 'storage'} or payload['storage'] != storage_identity():
        raise ValueError('storage_delete_target_changed')
    name = payload['name']
    if not isinstance(name, str) or not name or FileModel.objects.filter(file=name).exists():
        raise ValueError('storage_delete_object_referenced')
    # FileSystemStorage/S3 的 delete 对已不存在的键均幂等；中断后可安全重试。
    default_storage.delete(name)
