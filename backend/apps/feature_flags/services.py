"""灰度只控制功能投放；业务身份、权限和数据范围仍由业务接口检查。"""
import hashlib
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from apps.auth_app.sessions import locked_request_session
from apps.core.modules import module_enabled
from apps.logs.audit import write_audit, snapshot
from apps.permissions.models import UserRole
from apps.permissions.permissions import has_permission_code
from .models import FeatureFlag


class VersionConflict(APIException):
    status_code = 409
    default_detail = '记录已变化，请查看最新值后重试'


def bucket(flag, user_id):
    digest = hashlib.sha256(f'{flag.seed}:{user_id}'.encode()).digest()
    return int.from_bytes(digest[:8], 'big') % 10000


def evaluate(keys, user):
    """批量仅判定当前有效用户；无配置、停用模块或用户一律关闭。"""
    result = {key: False for key in keys}
    if not module_enabled('feature_flags') or not user or not user.is_authenticated:
        return result
    if not get_user_model().objects.filter(pk=user.pk, is_active=True, must_change_password=False).exists():
        return result
    user_id = str(user.pk)
    role_ids = set(str(value) for value in UserRole.objects.filter(user_id=user.pk, role__is_active=True)
                   .values_list('role_id', flat=True))
    for flag in FeatureFlag.objects.filter(key__in=keys, enabled=True):
        if user_id not in flag.excluded_users:
            result[flag.key] = (user_id in flag.included_users or bool(role_ids.intersection(flag.roles))
                                or bucket(flag, user_id) < flag.rollout)
    return result


def feature_enabled(key, user):
    """供业务服务在执行操作前调用；关闭模块时不触发开关数据库查询。"""
    return evaluate([key], user)[key]


def locked_actor(request, action):
    if not module_enabled('feature_flags'):
        raise NotFound()
    actor = get_user_model().objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if actor is None:
        raise AuthenticationFailed('登录凭据已撤销')
    if request.auth is not None:
        locked_request_session(request, actor)
    if actor.must_change_password or not has_permission_code(actor, 'feature_flag:' + action):
        raise PermissionDenied('没有特性开关操作权限')
    return actor


@transaction.atomic
def mutate(request, action, values, identifier=None):
    actor = locked_actor(request, action)
    row = None
    if action != 'create':
        row = FeatureFlag.objects.select_for_update().filter(pk=identifier).first()
        if row is None:
            raise NotFound()
        if values['version'] != row.version:
            raise VersionConflict()
    elif values['version'] != 0:
        raise VersionConflict()
    before = snapshot('feature_flag', row)
    if action == 'create':
        try:
            with transaction.atomic():
                row = FeatureFlag.objects.create(**{**values, 'version': 1})
        except IntegrityError:
            raise ValidationError({'key': '开关标识已存在'}) from None
    elif action == 'update':
        for field, value in values.items():
            if field != 'version':
                setattr(row, field, value)
        row.version += 1
        row.save()
    after = None if action == 'delete' else snapshot('feature_flag', row)
    write_audit(request=request, actor=actor, resource='feature_flag', identifier=row.pk,
                action=action, before=before, after=after)
    if action == 'delete':
        row.delete()
        return None
    return row
