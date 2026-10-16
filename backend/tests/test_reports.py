import pytest

from apps.reports.models import ReportDefinition

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'reports')
    settings.ROOT_URLCONF = 'tests.reports_urls'


def definition(**overrides):
    value = {
        'data_source': 'tasks', 'chart_type': 'bar',
        'dimensions': [{'field': 'status'}],
        'metric': {'field': 'id', 'aggregation': 'count'},
        'filters': [], 'limit': 20,
    }
    value.update(overrides)
    return value


def test_catalog_and_report_run(admin_client):
    catalog = admin_client.get('/api/v1/reports/catalog/')
    assert catalog.status_code == 200
    assert {item['key'] for item in catalog.json()['data']} >= {'users', 'tasks', 'files'}
    created = admin_client.post('/api/v1/reports/definitions/', {'name': '任务报表', 'code': 'task-report', 'kind': 'report', 'definition': definition()}, format='json')
    assert created.status_code == 201
    row = created.json()['data']
    assert admin_client.post(f"/api/v1/reports/definitions/{row['id']}/publish/", format='json').status_code == 200
    result = admin_client.get(f"/api/v1/reports/definitions/{row['id']}/run/")
    assert result.status_code == 200
    assert result.json()['data']['columns'] == ['status', 'value']


@pytest.mark.parametrize('bad', [
    {'data_source': 'unknown', 'chart_type': 'table', 'dimensions': [], 'metric': {'field': 'id', 'aggregation': 'count'}, 'filters': [], 'limit': 10},
    {'data_source': 'tasks', 'chart_type': 'table', 'dimensions': [{'field': 'sql'}], 'metric': {'field': 'id', 'aggregation': 'count'}, 'filters': [], 'limit': 10},
    {'data_source': 'tasks', 'chart_type': 'table', 'dimensions': [], 'metric': {'field': 'progress', 'aggregation': 'count'}, 'filters': [], 'limit': 10},
    {'data_source': 'tasks', 'chart_type': 'table', 'dimensions': [], 'metric': {'field': 'id', 'aggregation': 'count'}, 'filters': [], 'limit': 101},
])
def test_invalid_or_arbitrary_definition_rejected(admin_client, bad):
    response = admin_client.post('/api/v1/reports/definitions/', {'name': '坏报表', 'code': 'unsafe-report', 'kind': 'report', 'definition': bad}, format='json')
    assert response.status_code == 400
    assert not ReportDefinition.objects.filter(code='unsafe-report').exists()


def test_published_report_is_immutable(admin_client):
    row = admin_client.post('/api/v1/reports/definitions/', {'name': '报表', 'code': 'immutable-report', 'kind': 'dashboard', 'definition': definition()}, format='json').json()['data']
    admin_client.post(f"/api/v1/reports/definitions/{row['id']}/publish/", format='json')
    assert admin_client.patch(f"/api/v1/reports/definitions/{row['id']}/", {'name': '改名'}, format='json').status_code == 400
