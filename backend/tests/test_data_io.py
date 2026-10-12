"""
数据导入导出测试
"""

import io

import pandas as pd
from openpyxl import Workbook

from apps.tasks.models import TaskRecord


def build_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(['username', 'email', 'first_name', 'last_name', 'phone'])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = 'import.xlsx'
    return buf


class TestExport:
    def test_export_csv_with_bom_and_rows(self, admin_client, member_user):
        res = admin_client.get('/api/v1/data-io/export/?resource=users&export_format=csv')
        assert res.status_code == 200
        text = res.content.decode('utf-8-sig')
        assert text.startswith('username')
        assert 'member' in text

    def test_export_xlsx_columns_match_registry(self, admin_client, member_user):
        res = admin_client.get('/api/v1/data-io/export/?resource=users&export_format=xlsx')
        assert res.status_code == 200
        df = pd.read_excel(io.BytesIO(res.content))
        assert list(df.columns) == ['username', 'email', 'first_name', 'last_name', 'phone']

    def test_export_invalid_format_rejected(self, admin_client):
        assert admin_client.get('/api/v1/data-io/export/?export_format=pdf').status_code == 400

    def test_member_forbidden(self, member_client):
        assert member_client.get('/api/v1/data-io/export/').status_code == 403


class TestTemplate:
    def test_template_headers(self, admin_client):
        res = admin_client.get('/api/v1/data-io/template/?resource=users')
        assert res.status_code == 200
        df = pd.read_excel(io.BytesIO(res.content))
        assert list(df.columns) == ['username', 'email', 'first_name', 'last_name', 'phone']


class TestImport:
    def test_import_mixed_rows(self, admin_client, member_user):
        f = build_xlsx([
            ['u1', 'u1@e.com', '一', '导', ''],
            ['u2', 'u2@e.com', '二', '导', ''],
            ['', 'no-username@e.com', '', '', ''],      # 缺用户名
            ['member', 'dup@e.com', '', '', ''],        # 与已有用户重名
        ])
        res = admin_client.post('/api/v1/data-io/import/', {'file': f, 'resource': 'users'}, format='multipart')
        assert res.status_code == 200
        task = res.json()['data']
        assert task['status'] == 'success'  # 同步执行（CELERY_TASK_ALWAYS_EAGER）
        assert task['result']['created'] == 2
        assert task['result']['failed'] == 2

    def test_import_retry_duplicates_fail(self, admin_client, member_user):
        f = build_xlsx([['u1', 'u1@e.com', '', '', '']])
        first = admin_client.post('/api/v1/data-io/import/', {'file': f, 'resource': 'users'}, format='multipart').json()
        retry = admin_client.post(f"/api/v1/data-io/import/{first['data']['id']}/", format='json').json()
        assert retry['code'] == 200
        assert retry['data']['result']['created'] == 0
        assert retry['data']['result']['failed'] == 1

    def test_import_rejects_unsupported_extension(self, admin_client):
        bad = io.BytesIO(b'x')
        bad.name = 'data.json'
        res = admin_client.post('/api/v1/data-io/import/', {'file': bad, 'resource': 'users'}, format='multipart')
        assert res.status_code == 400

    def test_import_creates_task_record(self, admin_client, member_user):
        f = build_xlsx([['u9', 'u9@e.com', '', '', '']])
        admin_client.post('/api/v1/data-io/import/', {'file': f, 'resource': 'users'}, format='multipart')
        record = TaskRecord.objects.filter(task_type='import', related_resource='users').first()
        assert record is not None
        assert record.creator.username == 'admin'

    def test_imported_user_has_unusable_password(self, admin_client):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        f = build_xlsx([['nopass', 'nopass@e.com', '', '', '']])
        admin_client.post('/api/v1/data-io/import/', {'file': f, 'resource': 'users'}, format='multipart')
        user = User.objects.get(username='nopass')
        assert not user.has_usable_password()
