"""本人资料及托管头像：白名单写入、版本冲突、私有存储与退休清理。"""
import hashlib
import io
import logging
import os
import uuid
import warnings
from collections.abc import Mapping

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps
from rest_framework import serializers
from apps.core.client_ip import request_ip
from rest_framework_simplejwt.utils import get_md5_hash_password

from apps.core.exceptions import APIError
from apps.core.modules import module_enabled
from apps.files.models import FileModel
from apps.logs.models import OperationLog
from apps.users.models import UserProfile
from .serializers import UserSerializer

User = get_user_model()
logger = logging.getLogger(__name__)
AVATAR_MAX_SIZE = 5 * 1024 * 1024
AVATAR_MAX_PIXELS = 4_000_000


class ProfileReadSerializer(UserSerializer):
    bio = serializers.SerializerMethodField()

    def get_bio(self, user) -> str:
        return getattr(getattr(user, 'profile', None), 'bio', '')

    class Meta(UserSerializer.Meta):
        fields = (*UserSerializer.Meta.fields, 'bio')


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping) and set(data) - set(self.fields):
            raise serializers.ValidationError({'non_field_errors': ['请求包含不允许编辑的字段']})
        return super().to_internal_value(data)


class ProfileVersionSerializer(StrictSerializer):
    profile_version = serializers.IntegerField(min_value=1)


class ProfileWriteSerializer(ProfileVersionSerializer):
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    phone = serializers.RegexField(r'^\+?[0-9 ()-]{3,20}$', required=False, allow_blank=True, max_length=20)
    bio = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class AvatarUploadSerializer(ProfileVersionSerializer):
    file = serializers.FileField()

    def validate_file(self, upload):
        if not 0 < upload.size <= AVATAR_MAX_SIZE:
            raise serializers.ValidationError('头像需为非空图片，大小不超过 5 MiB')
        formats = {'png': 'PNG', 'jpg': 'JPEG', 'jpeg': 'JPEG', 'webp': 'WEBP'}
        extension = os.path.splitext(upload.name)[1].lower().lstrip('.')
        if extension not in formats:
            raise serializers.ValidationError('头像仅支持 PNG、JPEG 或 WebP')
        from apps.files.antivirus import checked_upload
        original = upload
        upload = checked_upload(upload, stage='avatar_upload')
        content = upload.read(AVATAR_MAX_SIZE + 1)
        if upload is not original:
            upload.close()
        if len(content) > AVATAR_MAX_SIZE:
            raise serializers.ValidationError('头像大小不超过 5 MiB')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    if image.format != formats[extension] or image.width * image.height > AVATAR_MAX_PIXELS:
                        raise ValueError('invalid image')
                    image.verify()
                with Image.open(io.BytesIO(content)) as image:
                    normalized = ImageOps.fit(ImageOps.exif_transpose(image).convert('RGBA'),
                                              (256, 256), method=Image.Resampling.LANCZOS)
                    normalized.info.clear()
                    output = io.BytesIO()
                    normalized.save(output, format='PNG')
                    return output.getvalue()
        except Exception as exc:
            raise serializers.ValidationError('头像内容损坏、格式不符或超过 400 万像素') from exc


def require_avatar_module():
    if not module_enabled('files'):
        raise APIError('文件模块未启用，头像操作不可用', status_code=404)


def locked_user(request, version):
    user = User.objects.select_for_update().filter(pk=request.user.pk).first()
    if (user is None or not user.is_active or user.must_change_password
            or request.auth.get('session_version') != user.session_version
            or request.auth.get('hash_password') != get_md5_hash_password(user.password)):
        raise APIError('登录凭据已撤销', status_code=401)
    from .sessions import locked_request_session
    locked_request_session(request, user)
    if user.profile_version != version:
        raise APIError('个人资料已变化，请刷新后重试', status_code=409)
    return user


def audit(request, user, operation, fields=()):
    OperationLog.objects.create(user=user, action='update', resource='profile', resource_id=str(user.pk),
                               description=f'{operation}; fields={",".join(sorted(fields))}; version={user.profile_version}',
                               ip_address=request_ip(request) or '0.0.0.0')


@transaction.atomic
def update_profile(request, data):
    values = dict(data)
    user = locked_user(request, values.pop('profile_version'))
    bio = values.pop('bio', None)
    for field, value in values.items():
        setattr(user, field, value)
    if bio is not None:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.bio = bio
        profile.save(update_fields=['bio', 'updated_at'])
    user.profile_version += 1
    user.save(update_fields=[*values, 'profile_version', 'updated_at'])
    audit(request, user, 'edit_profile', (*values, *(['bio'] if bio is not None else [])))
    return user


def replace_avatar(request, data):
    require_avatar_module()
    content = data['file']
    # 上传前即登记退休状态及目标键；存储/绑定失败仍有可清理的持久记录。
    key = f'avatars/{request.user.pk}/{uuid.uuid4().hex}.png'
    with transaction.atomic():
        user = locked_user(request, data['profile_version'])
        asset = FileModel.objects.create(original_name='avatar.png', file=key, purpose='avatar', uploader=user,
                                        file_type='png', content_type='image/png', size=len(content),
                                        md5=hashlib.md5(content).hexdigest(), is_deleted=True, deleted_at=timezone.now())
    try:
        from apps.files.antivirus import checked_upload
        avatar = checked_upload(ContentFile(content, name='avatar.png'), stage='avatar_normalized')
        try:
            stored = asset.file.storage.save(key, avatar)
            from apps.files.antivirus import register_artifact
            register_artifact(asset.file)
        finally:
            avatar.close()
        if stored != key:
            asset.file.name = stored
            asset.save(update_fields=['file', 'updated_at'])
        with transaction.atomic():
            user = locked_user(request, data['profile_version'])
            previous_avatar = user.avatar_file
            asset.is_deleted = False
            asset.deleted_at = None
            asset.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
            user.avatar_file = asset
            user.profile_version += 1
            user.save(update_fields=['avatar_file', 'profile_version', 'updated_at'])
            if previous_avatar:
                previous_avatar.soft_delete(actor=user)
            audit(request, user, 'replace_avatar')
        return user
    except Exception as exc:
        try:
            asset.hard_delete()
        except Exception:
            # 失败元数据保持退休状态，交由保留期任务重试，不泄露存储异常。
            logger.warning('暂存头像清理失败，保留记录 %s', asset.pk)
        if isinstance(exc, APIError):
            raise
        raise APIError('头像存储暂时不可用，请重试', status_code=503) from exc


@transaction.atomic
def remove_avatar(request, data):
    require_avatar_module()
    user = locked_user(request, data['profile_version'])
    previous_avatar = user.avatar_file
    user.avatar_file = None
    user.avatar = ''
    user.profile_version += 1
    user.save(update_fields=['avatar_file', 'avatar', 'profile_version', 'updated_at'])
    if previous_avatar:
        previous_avatar.soft_delete(actor=user)
    audit(request, user, 'remove_avatar')
    return user
