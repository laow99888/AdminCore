"""菜单写入串行化，防止两个并发改父节点形成循环。"""
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import Menu


@transaction.atomic
def save_menu(serializer):
    menus = list(Menu.objects.select_for_update().order_by('id'))
    parents = {menu.pk: menu.parent_id for menu in menus}
    current = serializer.instance
    if current:
        current.refresh_from_db()
    parent = serializer.validated_data.get('parent', current.parent if current else None)
    seen = {current.pk} if current else set()
    cursor = parent.pk if parent else None
    if cursor is not None and cursor not in parents:
        raise ValidationError({'parent': '父菜单已被删除，请刷新后重试'})
    while cursor is not None:
        if cursor in seen:
            raise ValidationError({'parent': '菜单不能指向自身或子菜单'})
        seen.add(cursor)
        cursor = parents.get(cursor)
    return serializer.save()


@transaction.atomic
def delete_menu(menu):
    list(Menu.objects.select_for_update().order_by('id'))
    if menu.children.exists():
        raise ValidationError('请先移除或迁移子菜单，避免级联删除')
    menu.delete()
