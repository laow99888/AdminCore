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
    },
    'roles': {
        'label': '角色', 'importable': False, 'exportable': True,
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
        queryset = scope_queryset(FileModel.objects.filter(purpose='general', is_deleted=False), user, 'file', 'uploader_id', fallback='self')
        search_fields = ['original_name', 'description']
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
    return IMPORT_EXPORT_RESOURCES.get(name)
