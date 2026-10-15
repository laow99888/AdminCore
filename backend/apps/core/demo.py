"""独立演示数据边界；仅管理命令调用，不暴露为 API。"""
from contextlib import contextmanager
import hashlib
import hmac
import os
import re

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection


def validate_target():
    instance = os.getenv('ADMINCORE_DEMO_INSTANCE', '')
    token = os.getenv('ADMINCORE_DEMO_RESET_TOKEN', '')
    database = 'admincore_demo_' + instance
    if (os.getenv('DJANGO_ENV') != 'demo' or settings.ADMINCORE_PRESET != 'demo'
            or not re.fullmatch('[0-9a-f]{32}', instance)
            or not re.fullmatch('[0-9a-f]{64}', token)
            or os.getenv('DB_NAME') != database
            or connection.vendor != 'postgresql'
            or connection.settings_dict['NAME'] != database
            or settings.ADMINCORE_STORAGE_BACKEND != 'local'):
        raise CommandError('仅允许已隔离的演示 PostgreSQL 实例；拒绝初始化或重置')
    names = ('demo_admin', 'demo_editor', 'demo_viewer')
    passwords = [os.getenv(key, '') for key in (
        'ADMINCORE_ADMIN_PASSWORD', 'ADMINCORE_DEMO_EDITOR_PASSWORD', 'ADMINCORE_DEMO_VIEWER_PASSWORD')]
    if (os.getenv('ADMINCORE_ADMIN_USERNAME') != names[0]
            or len(set(passwords)) != 3
            or any(len(value) < 40 or len(set(value)) < 10 for value in passwords)):
        raise CommandError('演示账号必须使用本项目独立生成的随机凭据')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        if cursor.fetchone()[0] != database:
            raise CommandError('连接的实际数据库与演示目标不符，拒绝操作')
    signature = hmac.new(token.encode(), database.encode(), hashlib.sha256).hexdigest()
    return instance, token, 'demo-v1:' + signature, dict(zip(names, passwords))


@contextmanager
def demo_lock(instance):
    # Session lock survives flush and prevents concurrent seed/reset commands.
    key = int.from_bytes(hashlib.sha256(instance.encode()).digest()[:8], 'big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [key])
        if not cursor.fetchone()[0]:
            raise CommandError('演示初始化或重置正在执行，请稍后重试')
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [key])


def require_empty_database():
    from django.apps import apps
    for config in apps.get_app_configs():
        if config.name.startswith('apps.'):
            for model in config.get_models():
                if model._base_manager.exists():
                    raise CommandError('数据库已有业务记录且没有本实例演示标记，拒绝接管')


def seed_data(accounts):
    """固定场景、无外部地址和真实发送；演示账户均只能用于本项目。"""
    from datetime import timedelta
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from apps.core.models import (Department, OrganizationMembership, Post, UserPost,
                                  DataScopeGrant, DataDictionary, SystemConfig)
    from apps.permissions.models import Role, RolePermission, UserRole, Permission
    from apps.notifications.models import (Announcement, Notification, MessageTemplate,
                                           MessageTemplateVersion)
    from apps.approvals.models import ApprovalRequest
    from apps.example.models import WorkItem
    from apps.tasks.models import TaskRecord
    from apps.logs.models import OperationLog, LoginLog

    User = get_user_model()
    admin = User.objects.get(username='demo_admin')
    admin.must_change_password = False
    admin.save(update_fields=['must_change_password'])
    editor = User.objects.create_user('demo_editor', 'editor@example.invalid', accounts['demo_editor'])
    viewer = User.objects.create_user('demo_viewer', 'viewer@example.invalid', accounts['demo_viewer'])
    read_codes = ['user:read', 'role:read', 'file:download', 'approval:read', 'log:read',
                  'post:read', 'example:read']
    editor_codes = read_codes + ['file:upload', 'file:recycle', 'file:restore',
                                 'example:create', 'example:update']
    for person, name, codes in ((viewer, '演示只读用户', read_codes), (editor, '演示业务编辑', editor_codes)):
        role = Role.objects.create(name=name, description='独立演示角色；无用户授权、系统配置或批量管理权限')
        RolePermission.objects.bulk_create([RolePermission(role=role, permission=p)
                                           for p in Permission.objects.filter(code__in=codes)])
        UserRole.objects.create(user=person, role=role)
        for resource in ('user', 'file', 'example'):
            DataScopeGrant.objects.create(role=role, resource=resource, scope='self')

    company = Department.objects.create(name='演示总部', order=1)
    engineering = Department.objects.create(name='研发部', parent=company, order=2)
    operation = Department.objects.create(name='运营部', parent=company, order=3)
    post = Post.objects.create(code='demo_operator', name='业务专员', description='岗位仅作任职信息展示')
    for person, department in ((admin, company), (editor, engineering), (viewer, operation)):
        OrganizationMembership.objects.create(user=person, department=department)
        UserPost.objects.create(user=person, post=post)
    DataDictionary.objects.create(code='demo_priority', name='演示优先级',
        items=[{'label': '普通', 'value': 'normal'}, {'label': '紧急', 'value': 'high'}])
    SystemConfig.objects.create(key='brand.name', value='AdminCore 独立演示', updated_by=admin)
    now = timezone.now()
    Announcement.objects.create(title='欢迎体验 AdminCore', content='此为独立演示数据，请勿上传真实资料。',
        status='published', published_at=now, created_by=admin, updated_by=admin)
    Announcement.objects.create(title='演示公告草稿', content='仅管理端可见的草稿。', created_by=admin, updated_by=admin)
    for person in (admin, editor, viewer):
        Notification.objects.create(recipient=person, title='演示使用说明', content='编辑与访客只能访问各自数据。',
                                    sender=admin, link='/example')
    template = MessageTemplate.objects.create(code='demo-welcome', name='演示欢迎模板')
    MessageTemplateVersion.objects.create(template=template, number=1,
        subject='欢迎 {{name}}', body='欢迎使用独立演示环境。', variables=['name'], creator=admin)
    for status, title in (('pending', '演示采购申请'), ('approved', '演示请假申请'), ('rejected', '演示权限申请')):
        ApprovalRequest.objects.create(title=title, content='合成数据，不涉及真实业务。',
            applicant=editor, assignee=admin, status=status,
            decided_by=admin if status != 'pending' else None,
            decided_at=now if status != 'pending' else None)
    for owner in (admin, editor, viewer):
        for status in ('open', 'done'):
            WorkItem.objects.create(title=owner.username + (' 的待处理工单' if status == 'open' else ' 的已完成工单'),
                status=status, priority='high' if status == 'open' else 'normal',
                notes='用于演示数据范围隔离、筛选和版本冲突。', creator=owner)
    for status in ('success', 'failed', 'cancelled'):
        TaskRecord.objects.create(name='演示任务（' + status + '）', creator=admin, status=status,
            progress=100 if status == 'success' else 0, started_at=now - timedelta(minutes=2),
            completed_at=now, result={'demo': True},
            error='演示失败，不会自动重试' if status == 'failed' else '')
    OperationLog.objects.create(user=admin, action='create', resource='demo',
        description='创建独立演示数据', ip_address='127.0.0.1')
    LoginLog.objects.create(user=editor, username=editor.username, status='success', ip_address='127.0.0.1')
    seed_files(admin)


def seed_files(admin):
    import base64
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from django.utils import timezone
    from apps.files.models import FileModel

    # 内置1×1 PNG与纯文本，不下载外部样本；重复重置保留已有对象而不清理任意上传。
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWoQAAAAASUVORK5CYII=')
    for name, content, mime, deleted in (
            ('演示图片.png', png, 'image/png', False),
            ('回收站示例.txt', '这是合成演示文件。\n'.encode(), 'text/plain', True)):
        extension = name.rsplit('.', 1)[1]
        key = 'demo/' + os.environ['ADMINCORE_DEMO_INSTANCE'] + '/fixture.' + extension
        if not default_storage.exists(key):
            saved = default_storage.save(key, ContentFile(content))
            if saved != key:
                raise CommandError('演示文件目标发生冲突；保留现场供核查')
        FileModel.objects.create(original_name=name, file=key, file_type=extension, size=len(content),
            content_type=mime, uploader=admin, description='独立演示文件', is_deleted=deleted,
            deleted_at=timezone.now() if deleted else None, deleted_by=admin if deleted else None)
