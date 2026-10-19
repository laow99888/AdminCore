"""
导入导出资源注册表

新增资源需显式声明能力，未开放导入的资源不能创建模板或执行导入：
- fields: 导出白名单；用户模板与导入列复用该列表，日志按类型分别声明
- required: 必填列
- unique_field: 用于判重的字段
- create_row: 单行创建逻辑（返回 (对象, None) 或 (None, 错误信息)）
- permissions: 导出除 data_io:export 外仍需精确资源权限
- export_queryset(): 数据来源与列表使用同一范围策略
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework.exceptions import ValidationError as APIValidationError
from apps.core.sensitive import phone_input_field, validate_contact_email


def create_user_row(data):
    User = get_user_model()
    if User.objects.filter(username=data['username']).exists():
        return None, f"用户名 {data['username']} 已存在"
    # 错误报告只描述字段，不把原始联系方式写入任务记录。
    try:
        email = validate_contact_email(data.get('email', '') or '')
        validate_email(email)
        phone = phone_input_field().run_validation(data.get('phone', '') or '')
    except (ValidationError, APIValidationError):
        return None, '邮箱或手机号格式无效，不能导入脱敏值'
    # 使用与 ModelSerializer 相同的模型字段校验，避免 SQLite 漏过 PostgreSQL 长度约束。
    try:
        values = {'username': data['username'], 'email': email,
                  'first_name': data.get('first_name', '') or '', 'last_name': data.get('last_name', '') or ''}
        for name, value in values.items():
            User._meta.get_field(name).clean(value, None)
    except ValidationError:
        return None, '用户字段格式或长度无效'
    user = User.objects.create_user(
        username=data['username'],
        email=email,
        first_name=data.get('first_name', '') or '',
        last_name=data.get('last_name', '') or '',
        phone=phone,
        # 未提供密码列时创建不可登录账号，由管理员重置密码
        password=None,
    )
    return user, None


def create_role_row(data):
    """只新增无授权角色，不导入角色成员、权限或数据范围。"""
    from apps.permissions.serializers import RoleSerializer
    serializer = RoleSerializer(data={**data, 'is_active': False})
    serializer.is_valid(raise_exception=True)
    return serializer.save(), None


def create_post_row(data):
    from apps.core.post_views import PostSerializer
    serializer = PostSerializer(data={**data, 'version': 1, 'is_active': False, 'order': 0})
    serializer.is_valid(raise_exception=True)
    return serializer.save(), None


def import_allowed(user, resource):
    """提交、模板、接续和每行写入共同复核当前权限。"""
    from apps.permissions.permissions import has_permission_code
    from apps.core.data_scope import unrestricted_user_creation
    from apps.core.modules import module_enabled
    from apps.core.tenancy import enabled, current_tenant_id
    if enabled() and current_tenant_id() is not None:
        from apps.core.models import Tenant, TenantMembership
        identifier = current_tenant_id()
        if not Tenant.objects.filter(pk=identifier, status=Tenant.STATUS_ACTIVE).exists():
            return False
        if not user or (not (user.is_staff or user.is_superuser) and not TenantMembership.objects.filter(
                tenant_id=identifier, user=user, is_active=True).exists()):
            return False
    config = get_resource(resource)
    if config and config.get('business'):
        from .business import require
        from rest_framework.exceptions import APIException
        try:
            require(user, resource)
            return True
        except APIException:
            return False
    if not config or not config['importable'] or not has_permission_code(user, 'data_io:import'):
        return False
    if not all(has_permission_code(user, code) for code in config['import_permissions']):
        return False
    if config.get('module') and not module_enabled(config['module']):
        return False
    if resource == 'users':
        return unrestricted_user_creation(user)
    # 与角色/岗位的人工写入口一致，不能通过导入绕过管理员限制。
    return bool(user.is_staff or user.is_superuser)


IMPORT_EXPORT_RESOURCES = {
    'users': {
        'label': '用户',
        'fields': ['username', 'email', 'first_name', 'last_name', 'phone'],
        'required': ['username', 'email'],
        'unique_field': 'username',
        'create_row': create_user_row,
        'importable': True,
        'exportable': True,
        'permissions': ('user:read',),
        'import_permissions': ('user:create',),
    },
    'roles': {
        'label': '角色', 'importable': True, 'exportable': True,
        'import_permissions': ('role:update',),
        'import_fields': ['name', 'description'], 'required': ['name'],
        'create_row': create_role_row,
        'permissions': ('role:read',),
        'fields': ['id', 'name', 'description', 'is_active', 'created_at'],
    },
    'logs': {
        'label': '日志', 'importable': False, 'exportable': True,
        'permissions': ('log:read',),
        # 原始描述、异常内容和请求路径可能带业务凭据，批量下载仅提供审计元数据。
        'fields': {
            'operation': ['id', 'created_at', 'user__username', 'action', 'resource', 'resource_id', 'status', 'ip_address'],
            'login': ['id', 'created_at', 'username', 'status', 'ip_address'],
            'exception': ['id', 'created_at', 'user__username', 'level', 'request_method', 'ip_address'],
        },
    },
    'files': {
        'label': '文件元数据', 'importable': False, 'exportable': True,
        'permissions': ('file:download',),
        'fields': ['id', 'original_name', 'file_type', 'size', 'content_type', 'uploader__username', 'download_count', 'created_at'],
    },
    'posts': {
        'label': '岗位', 'importable': True, 'exportable': True, 'module': 'organization',
        'permissions': ('post:read',), 'import_permissions': ('post:update',),
        'import_fields': ['code', 'name', 'description'], 'required': ['code', 'name'],
        'fields': ['id', 'code', 'name', 'description', 'order', 'is_active', 'created_at'],
        'create_row': create_post_row,
    },
}


def export_queryset(resource, user, filters):
    """与资源列表使用同一对象范围，只返回白名单字段，不读取文件内容。"""
    from django.db.models import Q
    from rest_framework.filters import SearchFilter
    from apps.core.data_scope import scope_queryset
    if resource == 'users':
        queryset = scope_queryset(get_user_model().objects.filter(is_staff=False, is_superuser=False), user, 'user', 'pk')
        search_fields = ['username', 'first_name', 'last_name']
    elif resource == 'roles':
        from apps.permissions.models import Role
        queryset = Role.objects.all()
        search_fields = ['name']
    elif resource == 'files':
        from apps.files.models import FileModel
        from apps.files.access import file_queryset_for_actor
        queryset = file_queryset_for_actor(FileModel.objects.filter(purpose='general', is_deleted=False), user)
        search_fields = ['original_name', 'description']
    elif resource == 'posts':
        from apps.core.models import Post
        queryset = Post.objects.all()
        search_fields = ['code', 'name']
    else:
        from apps.logs.models import OperationLog, LoginLog, ExceptionLog
        kind = filters.get('log_type', 'operation')
        model = {'operation': OperationLog, 'login': LoginLog, 'exception': ExceptionLog}[kind]
        queryset = scope_queryset(model.objects.all(), user, 'log', 'user_id')
        search_fields = {'operation': ['description', 'user__username'], 'login': ['username'], 'exception': ['message', 'request_path']}[kind]
    for key, value in filters.items():
        if key not in {'resource', 'export_format', 'search', 'log_type'}:
            queryset = queryset.filter(**{('resource' if key == 'resource_name' else key): value})
    # 复用 DRF 的搜索词切分，多个词之间为 AND，与列表 API 一致。
    if filters.get('search'):
        class SearchRequest:
            query_params = {'search': filters['search']}
        for term in SearchFilter().get_search_terms(SearchRequest()):
            condition = Q()
            for field in search_fields:
                condition |= Q(**{field + '__icontains': term})
            queryset = queryset.filter(condition)
    return queryset.order_by('-created_at', 'pk')


def get_resource(name):
    """获取资源配置，不存在返回 None"""
    return all_resources().get(name)


def all_resources():
    from .business import resources
    return {**IMPORT_EXPORT_RESOURCES, **resources()}
