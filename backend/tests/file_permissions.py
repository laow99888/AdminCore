"""仅被文件内容读写场景显式调用的授权夹具，不提升默认 member。"""
from apps.permissions.models import Permission, Role, RolePermission, UserRole


def grant_files(user, *codes):
    role, _ = Role.objects.get_or_create(name='文件测试-' + str(user.pk))
    UserRole.objects.get_or_create(user=user, role=role)
    for code in codes:
        resource, action = code.split(':')
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': code, 'resource': resource, 'action': action})
        RolePermission.objects.get_or_create(role=role, permission=permission)
    return role
