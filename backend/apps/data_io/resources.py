"""
导入导出资源注册表

新增可导入/导出的资源时，在这里注册即可：
- fields: 模板列与导入列（顺序即列顺序）
- required: 必填列
- unique_field: 用于判重的字段
- create_row: 单行创建逻辑（返回 (对象, None) 或 (None, 错误信息)）
- export_queryset: 导出数据来源
"""

from django.contrib.auth import get_user_model


def create_user_row(data):
    User = get_user_model()
    if User.objects.filter(username=data['username']).exists():
        return None, f"用户名 {data['username']} 已存在"
    user = User.objects.create_user(
        username=data['username'],
        email=data.get('email', '') or '',
        first_name=data.get('first_name', '') or '',
        last_name=data.get('last_name', '') or '',
        phone=data.get('phone', '') or '',
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
        'export_queryset': lambda: get_user_model().objects.filter(is_staff=False).order_by('date_joined'),
    },
}


def get_resource(name):
    """获取资源配置，不存在返回 None"""
    return IMPORT_EXPORT_RESOURCES.get(name)
