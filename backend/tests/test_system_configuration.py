from django.test import override_settings
from apps.core.models import SystemConfig, DataDictionary
from apps.core.system_config import config_value
from apps.logs.models import OperationLog
import pytest

pytestmark = pytest.mark.django_db
CONFIG = '/api/v1/system/config/'
DICTS = '/api/v1/system/dictionaries/'


def test_config_list_validation_conflict_audit_and_cache(admin_client):
    rows = admin_client.get(CONFIG).json()['data']
    assert len(rows) == 5 and all(row['version'] == 0 for row in rows)
    url = CONFIG + 'files.retention_days/'
    for invalid in [True, '30', 0, 3651, 1.5]:
        assert admin_client.patch(url, {'value': invalid, 'version': 0}, format='json').status_code == 400
    assert admin_client.patch(url, {'value': 45, 'version': 0}, format='json').status_code == 200
    assert config_value('files.retention_days') == 45
    assert admin_client.patch(url, {'value': 60, 'version': 0}, format='json').status_code == 409
    assert config_value('files.retention_days') == 45
    assert admin_client.patch(url, {'value': 60, 'version': 1}, format='json').status_code == 200
    assert config_value('files.retention_days') == 60
    assert OperationLog.objects.filter(resource='system_config').count() == 2
    assert SystemConfig.objects.get(key='files.retention_days').version == 2


def test_unknown_security_parameters_and_unprivileged_writes_denied(admin_client, member_client):
    assert admin_client.patch(CONFIG + 'DJANGO_SECRET_KEY/', {'value': 'secret', 'version': 0}, format='json').status_code == 404
    assert member_client.get(CONFIG).status_code == 403
    assert member_client.patch(CONFIG + 'brand.name/', {'value': '盗用', 'version': 0}, format='json').status_code == 403


def test_public_brand_only_whitelisted_and_disabled_fallback(admin_client, client):
    admin_client.patch(CONFIG + 'brand.name/', {'value': '示例产品', 'version': 0}, format='json')
    assert client.get('/api/v1/brand/').json()['data'] == {'name': '示例产品', 'tagline': '现代化中后台管理系统', 'logo': ''}
    with override_settings(ADMINCORE_MODULES=()):
        assert client.get('/api/v1/brand/').json()['data']['name'] == 'AdminCore'


def test_dictionary_crud_options_cache_and_version(admin_client, member_client):
    data = {'code': 'customer_level', 'name': '客户等级', 'version': 0,
            'items': [{'label': '普通', 'value': 'normal', 'order': 2}, {'label': '停用', 'value': 'old', 'is_active': False},
                      {'label': '重点', 'value': 'vip', 'order': 1}]}
    response = admin_client.post(DICTS, data, format='json')
    assert response.status_code == 201, response.data
    identifier = response.json()['data']['id']
    url = DICTS + identifier + '/'
    options = DICTS + 'options/customer_level/'
    assert member_client.get(DICTS).status_code == 403
    assert [item['value'] for item in member_client.get(options).json()['data']['items']] == ['vip', 'normal']
    assert admin_client.patch(url, {'name': '修改'}, format='json').status_code == 400
    assert admin_client.patch(url, {'name': '修改', 'version': 0}, format='json').status_code == 409
    assert admin_client.patch(url, {'name': '修改', 'items': [{'label': '新值', 'value': 'new'}], 'version': 1}, format='json').status_code == 200
    assert member_client.get(options).json()['data']['items'][0]['value'] == 'new'
    assert admin_client.patch(url, {'code': 'new_code', 'version': 2}, format='json').status_code == 400
    assert admin_client.patch(url, {'is_active': False, 'version': 2}, format='json').status_code == 200
    assert member_client.get(options).status_code == 404
    assert admin_client.delete(url).status_code == 405
    assert DataDictionary.objects.filter(pk=identifier).exists()
    assert OperationLog.objects.filter(resource='dictionary').count() == 3


@pytest.mark.parametrize('items', [[{'label': '重复', 'value': 'x'}, {'label': '重复', 'value': 'x'}],
                                  [{'label': '', 'value': 'x'}], [{'label': '数值', 'value': 1}],
                                  [{'label': '非法', 'value': 'x', 'order': -1}], [{'label': '非法', 'value': 'x', 'script': 'code'}]])
def test_invalid_dictionary_items_rejected(admin_client, items):
    assert admin_client.post(DICTS, {'code': 'test', 'name': '测试', 'version': 0, 'items': items}, format='json').status_code == 400
    assert DataDictionary.objects.count() == 0


def test_state_machine_dictionary_cannot_be_created(admin_client):
    assert admin_client.post(DICTS, {'code': 'task_status', 'name': '任务状态', 'version': 0, 'items': []}, format='json').status_code == 400


def test_logo_validation_normalization_audit_and_removal(admin_client, member_client, client):
    import base64
    import io
    from PIL import Image, PngImagePlugin
    raw = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('Comment', 'private-metadata')
    Image.new('RGB', (400, 200), 'blue').save(raw, format='PNG', pnginfo=metadata)
    source = 'data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode()
    url = CONFIG + 'brand.logo/'
    assert member_client.patch(url, {'value': source, 'version': 0}, format='json').status_code == 403
    for invalid in ['https://example.com/logo.png', 'data:image/svg+xml;base64,PHN2Zy8+', 'data:image/png;base64,bad!', True,
                    'data:image/png;base64,' + base64.b64encode(b'x' * (201 * 1024)).decode()]:
        assert admin_client.patch(url, {'value': invalid, 'version': 0}, format='json').status_code == 400
    assert admin_client.patch(url, {'value': source, 'version': 0}, format='json').status_code == 200
    logo = client.get('/api/v1/brand/').json()['data']['logo']
    with Image.open(io.BytesIO(base64.b64decode(logo.split(',')[1]))) as image:
        assert image.size == (256, 128) and 'Comment' not in image.info
    log = OperationLog.objects.filter(resource='system_config', resource_id='brand.logo').get()
    assert 'data:image' not in log.description and 'private-metadata' not in log.description
    assert admin_client.patch(url, {'value': '', 'version': 0}, format='json').status_code == 409
    assert admin_client.patch(url, {'value': '', 'version': 1}, format='json').status_code == 200
    assert client.get('/api/v1/brand/').json()['data']['logo'] == ''


def test_normalized_logo_can_be_read_repeatedly():
    import base64
    import io
    import random
    from PIL import Image
    from apps.core.system_config import validate_logo
    raw = io.BytesIO()
    image = Image.frombytes('RGB', (300, 300), random.Random(42).randbytes(300 * 300 * 3))
    image.save(raw, format='JPEG', quality=90)
    normalized = validate_logo('data:image/jpeg;base64,' + base64.b64encode(raw.getvalue()).decode())
    assert len(base64.b64decode(normalized.split(',')[1])) <= 200 * 1024
    assert validate_logo(normalized) == normalized
