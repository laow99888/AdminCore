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
from .permissions import HasPermission, IsAdmin, permission_codes
from apps.auth_app.write_authorization import authorize_write


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('RoleDetailResponse', RoleSerializer())),
    create=extend_schema(responses={201: envelope('RoleCreatedResponse', RoleSerializer())}),
    update=extend_schema(responses={200: envelope('RoleUpdatedResponse', RoleSerializer()), 400: MessageResponse, 409: MessageResponse}),
    partial_update=extend_schema(responses={200: envelope('RolePatchedResponse', RoleSerializer()), 400: MessageResponse, 409: MessageResponse}),
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

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            permissions.append(IsAdmin())
        return permissions

    def get_queryset(self):
        return Role.objects.prefetch_related('permissions__permission').all()

    @transaction.atomic
    def perform_create(self, serializer):
        from apps.logs.audit import snapshot, write_audit
        authorize_write(self.request, 'role:update', admin=True)
        row = serializer.save()
        write_audit(request=self.request, resource='role', identifier=row.pk, action='create', after=snapshot('role', row))

    @transaction.atomic
    def perform_update(self, serializer):
        from apps.logs.audit import snapshot, write_audit
        authorize_write(self.request, 'role:update', admin=True)
        serializer.instance = Role.objects.select_for_update().get(pk=serializer.instance.pk)
        before = snapshot('role', serializer.instance)
        row = serializer.save()
        write_audit(request=self.request, resource='role', identifier=row.pk, before=before, after=snapshot('role', row))

    @transaction.atomic
    def perform_destroy(self, instance):
        from apps.logs.audit import snapshot, write_audit
        authorize_write(self.request, 'role:update', admin=True)
        row = Role.objects.select_for_update().get(pk=instance.pk)
        write_audit(request=self.request, resource='role', identifier=row.pk, action='delete', before=snapshot('role', row))
        row.delete()


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('PermissionDetailResponse', PermissionSerializer())),
)
class PermissionViewSet(EnvelopeResponseMixin, viewsets.ReadOnlyModelViewSet):
    """权限管理（只读）"""
    # 响应 Mixin 提供 create/update/destroy，路由器会据此误登记写方法；
    # 显式限制方法，同时保证运行时与 OpenAPI 均保持只读。
    http_method_names = ['get', 'head', 'options']
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['resource', 'action']
    search_fields = ['name', 'code']
    ordering_fields = ['code', 'name', 'resource', 'action', 'created_at']
    ordering = ['code']


@extend_schema_view(
    retrieve=extend_schema(responses=envelope('MenuDetailResponse', MenuSerializer())),
    create=extend_schema(responses={201: envelope('MenuCreatedResponse', MenuSerializer())}),
    update=extend_schema(responses={200: envelope('MenuUpdatedResponse', MenuSerializer()), 400: MessageResponse, 409: MessageResponse}),
    partial_update=extend_schema(responses={200: envelope('MenuPatchedResponse', MenuSerializer()), 400: MessageResponse, 409: MessageResponse}),
    destroy=extend_schema(responses={200: MessageResponse}),
    my_menu=extend_schema(responses=envelope('MyMenuResponse', MenuSerializer(many=True)), filters=False),
)
class MenuViewSet(EnvelopeResponseMixin, viewsets.ModelViewSet):
    """菜单维护及按权限过滤的导航树。"""
    queryset = Menu.objects.filter(is_visible=True, parent=None)
    serializer_class = MenuSerializer
    ordering_fields = ['order', 'name', 'created_at']
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
            return Menu.objects.filter(is_visible=True, parent=None, id__in=self.allowed_menu_ids())
        return Menu.objects.filter(is_visible=True, parent=None, id__in=self.allowed_menu_ids())

    def allowed_menu_ids(self):
        codes = permission_codes(self.request.user)
        menus = list(Menu.objects.filter(is_visible=True).select_related('permission'))
        from apps.core.modules import path_enabled
        menus = [menu for menu in menus if path_enabled(menu.path)]
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            menus = [menu for menu in menus if not any(menu.path == base or menu.path.startswith(base + '/')
                                                      for base in ('/organization', '/reliability'))]
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
        children = {}
        for menu in Menu.objects.all():
            children.setdefault(menu.parent_id, []).append(menu)
        context['menu_children'] = children
        if self.action == 'my_menu':
            context['allowed_menu_ids'] = self.allowed_menu_ids()
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        from .services import save_menu
        from apps.logs.audit import snapshot, write_audit
        authorize_write(self.request, 'menu:update')
        row = save_menu(serializer)
        write_audit(request=self.request, resource='menu', identifier=row.pk, action='create', after=snapshot('menu', row))

    @transaction.atomic
    def perform_update(self, serializer):
        from .services import save_menu
        from apps.logs.audit import snapshot, write_audit
        authorize_write(self.request, 'menu:update')
        # 与菜单服务统一锁顺序，避免并发树修改/审计快照不一致。
        list(Menu.objects.select_for_update().order_by('id'))
        serializer.instance.refresh_from_db()
        before = snapshot('menu', serializer.instance)
        row = save_menu(serializer)
        write_audit(request=self.request, resource='menu', identifier=row.pk, before=before, after=snapshot('menu', row))

    @transaction.atomic
    def perform_destroy(self, instance):
        from .services import delete_menu
        from apps.logs.audit import snapshot, write_audit
        authorize_write(self.request, 'menu:update')
        list(Menu.objects.select_for_update().order_by('id'))
        instance.refresh_from_db()
        before, identifier = snapshot('menu', instance), instance.pk
        delete_menu(instance)
        write_audit(request=self.request, resource='menu', identifier=identifier, action='delete', before=before)

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
