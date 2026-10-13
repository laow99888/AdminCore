"""
端到端冒烟测试（开发验证用，不属于测试套件）

运行：venv/Scripts/python.exe smoke_test.py
覆盖：登录、文件上传/列表/下载/软删除、通知发送/未读数/已读、任务记录查询
"""

import io
import os
import sys
from unittest.mock import patch

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.testing')

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment
from rest_framework.test import APIClient

setup_test_environment()
runner = DiscoverRunner(interactive=False, verbosity=0)
old_config = runner.setup_databases()

failures = []


def check(name, condition, detail=''):
    mark = 'PASS' if condition else 'FAIL'
    print(f'[{mark}] {name}' + (f' — {detail}' if detail and not condition else ''))
    if not condition:
        failures.append(name)


try:
    User = get_user_model()
    admin = User.objects.create_superuser('admin', 'admin@example.com', 'Admin#12345')
    member = User.objects.create_user('member', 'member@example.com', 'Member#12345')

    client = APIClient()

    # --- 登录 ---
    res = client.post('/api/v1/auth/login/', {'username': 'admin', 'password': 'Admin#12345'}, format='json')
    check('管理员登录', res.status_code == 200, f'status={res.status_code} body={res.content[:300]}')
    login_data = res.json() if res.status_code == 200 else {}
    # CustomTokenObtainPairSerializer 返回平铺结构（access/refresh/user）
    access = login_data.get('access') or login_data.get('data', {}).get('access')
    check('登录返回 access token', bool(access))
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

    # --- /auth/me ---
    res = client.get('/api/v1/auth/me/')
    check('获取当前用户 /auth/me', res.status_code == 200, f'status={res.status_code}')

    # --- 文件上传（合法类型） ---
    upload = io.BytesIO(b'smoke test content for AdminCore')
    upload.name = 'smoke-test.txt'
    res = client.post('/api/v1/files/', {'file': upload, 'description': 'smoke'}, format='multipart')
    check('文件上传（txt 白名单内）', res.status_code == 201, f'status={res.status_code} body={res.content[:300]}')
    file_id = None
    if res.status_code == 201:
        payload = res.json()
        file_id = payload.get('id') if isinstance(payload, dict) else None

    # --- 文件上传（非法类型被拒绝） ---
    bad = io.BytesIO(b'binary')
    bad.name = 'virus.exe'
    res = client.post('/api/v1/files/', {'file': bad}, format='multipart')
    check('文件上传（exe 白名单外拒绝）', res.status_code == 400, f'status={res.status_code}')

    # --- 文件列表 ---
    res = client.get('/api/v1/files/')
    ok = res.status_code == 200
    body = res.json() if ok else {}
    # 分页响应可能为 {results: []} 或 {items: []}
    items = (body.get('data') or {}).get('items') or [] if ok else []
    check('文件列表', ok and len(items) >= 1, f'status={res.status_code} body={str(body)[:300]}')

    # --- 文件下载 ---
    if file_id:
        res = client.get(f'/api/v1/files/{file_id}/download/')
        content = b''.join(res.streaming_content) if res.status_code == 200 else b''
        check('文件下载', res.status_code == 200 and content == b'smoke test content for AdminCore',
              f'status={res.status_code}')

    # --- 通知：管理员发送 ---
    res = client.post('/api/v1/notifications/', {
        'recipient_ids': [str(member.id)], 'title': '欢迎使用 AdminCore', 'content': '冒烟测试通知',
    }, format='json')
    check('发送通知（管理员）', res.status_code == 201, f'status={res.status_code} body={res.content[:300]}')

    # --- 通知：member 登录查看/未读数/标记已读 ---
    res = client.post('/api/v1/auth/login/', {'username': 'member', 'password': 'Member#12345'}, format='json')
    member_access = (res.json().get('access') if res.status_code == 200 else None)
    check('普通用户登录', bool(member_access))
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {member_access}')

    res = client.get('/api/v1/notifications/unread_count/')
    ok = res.status_code == 200
    count = res.json().get('data', {}).get('count') if ok else None
    check('未读通知数 = 1', ok and count == 1, f'status={res.status_code} body={res.content[:200]}')

    res = client.post('/api/v1/notifications/mark_all_read/')
    check('全部标记已读', res.status_code == 200, f'status={res.status_code}')

    res = client.get('/api/v1/notifications/unread_count/')
    count = res.json().get('data', {}).get('count') if res.status_code == 200 else None
    check('标记后未读数 = 0', count == 0)

    # --- 权限隔离：普通用户访问任务中心应被拒 ---
    res = client.get('/api/v1/tasks/')
    check('任务中心对普通用户返回 403', res.status_code == 403, f'status={res.status_code}')

    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    res = client.get('/api/v1/tasks/')
    check('任务中心管理员可访问', res.status_code == 200, f'status={res.status_code}')

    # --- 软删除文件 ---
    if file_id:
        res = client.delete(f'/api/v1/files/{file_id}/')
        check('文件软删除', res.status_code == 204, f'status={res.status_code}')
        res = client.get('/api/v1/files/')
        body = res.json() if res.status_code == 200 else {}
        items = (body.get('data') or {}).get('items') or [] if res.status_code == 200 else []
        check('软删除后列表不含该文件', len(items) == 0)

    # --- 操作日志已记录 ---
    res = client.get('/api/v1/logs/operation/')
    ok = res.status_code == 200
    body = res.json() if ok else {}
    items = (body.get('data') or {}).get('items') or [] if ok else []
    actions = {item.get('action') for item in items}
    check('操作日志记录 upload/download/delete', {'upload', 'download', 'delete'} <= actions,
          f'actions={actions}')

    # ========== 数据导入导出 ==========
    import pandas as pd

    # 导出 CSV（含 BOM + 表头）
    res = client.get('/api/v1/data-io/export/?resource=users&export_format=csv')
    csv_text = res.content.decode('utf-8-sig')
    check('导出用户 CSV', res.status_code == 200 and csv_text.startswith('username') and 'member' in csv_text,
          f'status={res.status_code}')

    # 导出 xlsx
    res = client.get('/api/v1/data-io/export/?resource=users&export_format=xlsx')
    xlsx_ok = res.status_code == 200
    if xlsx_ok:
        df = pd.read_excel(io.BytesIO(res.content))
        xlsx_ok = list(df.columns) == ['username', 'email', 'first_name', 'last_name', 'phone']
    check('导出用户 xlsx（列与注册表一致）', xlsx_ok, f'status={res.status_code}')

    # 下载导入模板
    res = client.get('/api/v1/data-io/template/?resource=users')
    tpl_ok = res.status_code == 200
    if tpl_ok:
        df = pd.read_excel(io.BytesIO(res.content))
        tpl_ok = list(df.columns) == ['username', 'email', 'first_name', 'last_name', 'phone']
    check('下载导入模板 xlsx', tpl_ok, f'status={res.status_code}')

    # Excel 导入：2 行有效 + 1 行缺邮箱 + 1 行与 member 重名
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['username', 'email', 'first_name', 'last_name', 'phone'])
    ws.append(['imported1', 'i1@example.com', '一', '导', '13800000001'])
    ws.append(['imported2', 'i2@example.com', '二', '导', '13800000002'])
    ws.append(['noemail_user', '', '缺', '邮', ''])
    ws.append(['member', 'dup@example.com', '重', '复', ''])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = 'import-users.xlsx'
    res = client.post('/api/v1/data-io/import/', {'file': buf, 'resource': 'users'}, format='multipart')
    ok = res.status_code == 200
    task_data = res.json().get('data') if ok else {}
    check('提交导入任务', ok and task_data.get('status') in ('success', 'running', 'pending'),
          f'status={res.status_code} body={res.content[:300]}')

    task_id = task_data.get('id')
    if task_id:
        res = client.get(f'/api/v1/data-io/import/{task_id}/')
        check('导入任务完成且统计正确（2 成功 2 失败）',
              res.json().get('data', {}).get('status') == 'success'
              and (res.json().get('data', {}).get('result') or {}).get('created') == 2
              and (res.json().get('data', {}).get('result') or {}).get('failed') == 2,
              f'result={res.json().get("data", {}).get("result")}')
        result = res.json().get('data', {}).get('result') or {}
        err_msgs = ' '.join(e.get('message', '') for e in (result.get('errors') or []))
        check('行级错误含必填为空与重名提示', '必填字段为空' in err_msgs and '已存在' in err_msgs, f'errors={err_msgs}')

        # 重试：重跑同一文件，4 行全部因重名失败
        res = client.post(f'/api/v1/data-io/import/{task_id}/', format='json')
        retry_data = res.json().get('data') if res.status_code == 200 else {}
        retry_result = retry_data.get('result') or {}
        check('导入重试（重复数据全部失败）',
              res.status_code == 200 and retry_data.get('status') == 'success'
              and retry_result.get('created') == 0 and retry_result.get('failed') == 4,
              f'status={res.status_code} result={retry_result}')

    # 导入的账号不可登录（未设置密码）
    imported = User.objects.filter(username='imported1').first()
    check('导入用户存在且密码不可用', imported is not None and not imported.has_usable_password())

    # ========== 审批流程 ==========
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {member_access}')

    # member 向 admin 提交两个申请
    res = client.post('/api/v1/approvals/', {
        'title': '测试采购申请', 'request_type': 'purchase',
        'content': '采购开发用显示器一台', 'assignee_id': str(admin.id),
    }, format='json')
    check('提交审批申请', res.status_code == 201, f'status={res.status_code} body={res.content[:300]}')
    req1_id = res.json().get('data', {}).get('id') if res.status_code == 201 else None

    res = client.post('/api/v1/approvals/', {
        'title': '测试请假申请', 'request_type': 'leave',
        'content': '10-14 请年假一天', 'assignee_id': str(admin.id),
    }, format='json')
    req2_id = res.json().get('data', {}).get('id') if res.status_code == 201 else None

    # member 看到的"我发起的"应含 2 条
    res = client.get('/api/v1/approvals/?box=sent')
    items = (res.json().get('data') or {}).get('items') or [] if res.status_code == 200 else []
    check('我的申请列表（2 条）', res.status_code == 200 and len(items) == 2, f'len={len(items)}')

    # 非审批人不能处理
    if req1_id:
        res = client.post(f'/api/v1/approvals/{req1_id}/approve/', {}, format='json')
        check('非审批人处理申请返回 403', res.status_code == 403, f'status={res.status_code}')

    # admin 待办 + 收到通知
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    res = client.get('/api/v1/approvals/?box=todo')
    items = (res.json().get('data') or {}).get('items') or [] if res.status_code == 200 else []
    check('admin 待办列表（2 条）', res.status_code == 200 and len(items) == 2, f'len={len(items)}')

    res = client.get('/api/v1/notifications/?scope=all&notification_type=approval')
    items = (res.json().get('data') or {}).get('items') or [] if res.status_code == 200 else []
    check('审批人收到提交通知', res.status_code == 200 and len(items) >= 2, f'len={len(items)}')

    # 通过申请 1
    if req1_id:
        res = client.post(f'/api/v1/approvals/{req1_id}/approve/', {'comment': '同意'}, format='json')
        check('通过申请', res.status_code == 200 and res.json().get('data', {}).get('status') == 'approved',
              f'status={res.status_code} body={res.content[:200]}')

    # admin 已办列表
    res = client.get('/api/v1/approvals/?box=done')
    items = (res.json().get('data') or {}).get('items') or [] if res.status_code == 200 else []
    check('admin 已办列表（1 条）', res.status_code == 200 and len(items) == 1, f'len={len(items)}')

    # member 撤回申请 2（先回到 member 身份）
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {member_access}')
    if req2_id:
        res = client.post(f'/api/v1/approvals/{req2_id}/cancel/', format='json')
        check('撤回自己的待审批申请', res.status_code == 200 and res.json().get('data', {}).get('status') == 'cancelled',
              f'status={res.status_code}')

        # 已撤回的申请不能再处理
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        res = client.post(f'/api/v1/approvals/{req2_id}/reject/', {}, format='json')
        check('已撤回申请不可再处理（400）', res.status_code == 400, f'status={res.status_code}')

    # ========== 仪表盘统计 ==========
    # 健康检查端点（必须返回合法 JSON 响应，不能是裸 dict）
    # SQLite 冒烟不连接在用 Redis；真实依赖就绪由部署健康检查验证。
    with patch('django_redis.get_redis_connection'):
        res = client.get('/api/v1/health/')
    check('健康检查端点', res.status_code == 200 and res.json().get('status') == 'ok',
          f'status={res.status_code}')

    # 错误密码登录（验证失败日志）
    res = client.post('/api/v1/auth/login/', {'username': 'member', 'password': 'wrong-pass'}, format='json')
    check('错误密码登录返回 401', res.status_code == 401, f'status={res.status_code}')

    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    res = client.get('/api/v1/dashboard/stats/')
    data = res.json().get('data', {}) if res.status_code == 200 else {}
    totals = data.get('totals', {})
    check('仪表盘统计总量（用户>=3）', res.status_code == 200 and totals.get('users', 0) >= 3,
          f'status={res.status_code} totals={totals}')
    trend = data.get('login_trend', [])
    check('7 日登录趋势且当日有成功/失败记录',
          isinstance(trend, list) and len(trend) == 7
          and trend[-1].get('success', 0) >= 2 and trend[-1].get('failed', 0) >= 1,
          f'trend={trend[-1] if trend else None}')
    check('任务状态分布含导入任务', data.get('task_status', {}).get('success', 0) >= 1,
          f'task_status={data.get("task_status")}')

    # member 收到申请通过通知
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {member_access}')
    res = client.get('/api/v1/notifications/?notification_type=approval')
    items = (res.json().get('data') or {}).get('items') or [] if res.status_code == 200 else []
    approved_notice = any('已通过' in (item.get('title') or '') for item in items)
    check('申请人收到通过通知', approved_notice, f'items={[i.get("title") for i in items]}')
finally:
    runner.teardown_databases(old_config)
    from django.test.utils import teardown_test_environment

    teardown_test_environment()
    from django.conf import settings
    from pathlib import Path
    import shutil
    import tempfile

    media_root = Path(settings.MEDIA_ROOT).resolve()
    if (not failures and sys.exc_info()[0] is None and getattr(settings, 'TESTING', False)
            and media_root.parent == Path(tempfile.gettempdir()).resolve()
            and media_root.name.startswith('admincore-test-media-')):
        shutil.rmtree(media_root)
        print(f'已清理本次冒烟媒体：{media_root}')
    else:
        print(f'保留冒烟媒体证据：{media_root}')

print()
if failures:
    print(f'共 {len(failures)} 项失败：{failures}')
    sys.exit(1)
print('全部通过 ✔')
