"""
权限系统视图
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from apps.core.schema import envelope, MessageResponse

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db import transaction
from apps.core.mixins import EnvelopeResponseMixin
from .models import Role, Permission, Menu
from .serializers import RoleSerializer, PermissionSerializer, MenuSerializer
from .permissions import HasPermission, permission_codes


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('RoleDetailResponse', RoleSerializer())),
    create=extend_schema(responses={201: envelope('RoleCreatedResponse', RoleSerializer())}),
    update=extend_schema(responses=envelope('RoleUpdatedResponse', RoleSerializer())),
    partial_update=extend_schema(responses=envelope('RolePatchedResponse', RoleSerializer())),
    destroy=extend_schema(responses={200: MessageResponse}),
)
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


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('PermissionDetailResponse', PermissionSerializer())),
)
class PermissionViewSet(EnvelopeResponseMixin, viewsets.ReadOnlyModelViewSet):
    """权限管理（只读）"""
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['resource', 'action']
    search_fields = ['name', 'code']
    ordering = ['code']


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('MenuDetailResponse', MenuSerializer())),
    create=extend_schema(responses={201: envelope('MenuCreatedResponse', MenuSerializer())}),
    update=extend_schema(responses=envelope('MenuUpdatedResponse', MenuSerializer())),
    partial_update=extend_schema(responses=envelope('MenuPatchedResponse', MenuSerializer())),
    destroy=extend_schema(responses={200: MessageResponse}),
    my_menu=extend_schema(responses=envelope('MyMenuResponse', MenuSerializer(many=True)), filters=False),
)
class MenuViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    """菜单维护及按权限过滤的导航树。"""
    queryset = Menu.objects.filter(is_visible=True, parent=None)
    serializer_class = MenuSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action != 'my_menu':
            self.required_permission = 'menu:update' if self.action in ('create', 'update', 'partial_update', 'destroy') else 'menu:read'
            return [IsAuthenticated(), HasPermission()]
        return super().get_permissions()

    def get_queryset(self):
        if self.action != 'my_menu':
            queryset = Menu.objects.all()
            return queryset.filter(parent=None) if self.action == 'list' else queryset
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
        context['manage_menus'] = self.action != 'my_menu'
        if self.action == 'my_menu':
            context['allowed_menu_ids'] = self.allowed_menu_ids()
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        from .services import save_menu
        self.audit_menu(save_menu(serializer), 'create')

    @transaction.atomic
    def perform_update(self, serializer):
        from .services import save_menu
        self.audit_menu(save_menu(serializer), 'update')

    @transaction.atomic
    def perform_destroy(self, instance):
        from .services import delete_menu
        menu_id, name = str(instance.id), instance.name
        delete_menu(instance)
        self.audit_menu_values(menu_id, name, 'delete')

    def audit_menu(self, menu, action):
        self.audit_menu_values(str(menu.id), menu.name, action)

    def audit_menu_values(self, menu_id, name, action):
        from apps.logs.models import OperationLog
        OperationLog.objects.create(user=self.request.user, action=action, resource='menu',
                                    resource_id=menu_id, description=f'{action} menu {name}',
                                    ip_address=self.request.META.get('REMOTE_ADDR', ''))

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
