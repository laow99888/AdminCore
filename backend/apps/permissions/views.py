"""
权限系统视图
"""

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from apps.core.mixins import EnvelopeResponseMixin
from .models import Role, Permission, Menu
from .serializers import RoleSerializer, PermissionSerializer, MenuSerializer
from .permissions import HasPermission, permission_codes


class RoleViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    """角色管理"""
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    permission_map = {'list': 'role:read', 'retrieve': 'role:read', 'create': 'role:update',
                      'update': 'role:update', 'partial_update': 'role:update', 'destroy': 'role:update'}
    filterset_fields = ['is_active']
    search_fields = ['name']
    ordering_fields = ['created_at', 'name']

    def get_queryset(self):
        return Role.objects.prefetch_related('permissions').all()


class PermissionViewSet(EnvelopeResponseMixin, viewsets.ReadOnlyModelViewSet):
    """权限管理（只读）"""
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['resource', 'action']
    search_fields = ['name', 'code']
    ordering = ['code']


class MenuViewSet(EnvelopeResponseMixin, viewsets.ReadOnlyModelViewSet):
    """菜单管理（只读）"""
    queryset = Menu.objects.filter(is_visible=True, parent=None)
    serializer_class = MenuSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action != 'my_menu':
            self.required_permission = 'menu:read'
            return [IsAuthenticated(), HasPermission()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        # 根据用户权限过滤菜单
        if user.is_superuser or user.is_staff:
            return Menu.objects.filter(is_visible=True, parent=None)
        return Menu.objects.filter(is_visible=True, parent=None, id__in=self.allowed_menu_ids())

    def allowed_menu_ids(self):
        codes = permission_codes(self.request.user)
        menus = list(Menu.objects.filter(is_visible=True).select_related('permission'))
        if '*' in codes:
            return {menu.id for menu in menus}
        by_id = {menu.id: menu for menu in menus}
        def accessible(menu, seen):
            if menu.id in seen or (menu.permission_id and menu.permission.code not in codes):
                return False
            if menu.parent_id:
                parent = by_id.get(menu.parent_id)
                return parent is not None and accessible(parent, seen | {menu.id})
            return True
        return {menu.id for menu in menus if accessible(menu, set())}

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['allowed_menu_ids'] = self.allowed_menu_ids()
        return context

    @action(detail=False, methods=['get'])
    def my_menu(self, request):
        """获取当前用户可访问的菜单"""
        menus = self.get_queryset()
        serializer = self.get_serializer(menus, many=True)
        return Response({
            'code': 200,
            'message': 'success',
            'data': serializer.data,
        })
