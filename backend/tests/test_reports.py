import pytest
from datetime import datetime, timezone

from apps.reports.models import ReportDefinition
from apps.tasks.models import TaskRecord
from apps.core.models import DataScopeGrant
from apps.permissions.models import Permission, Role, RolePermission, UserRole
from apps.files.models import FileModel, FileAccessGrant

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


def run_report(client, design):
    created = client.post('/api/v1/reports/definitions/', {
        'name': '聚合核对', 'code': 'aggregate-check', 'kind': 'report', 'definition': design,
    }, format='json')
    assert created.status_code == 201
    identifier = created.json()['data']['id']
    assert client.post(f'/api/v1/reports/definitions/{identifier}/publish/', format='json').status_code == 200
    response = client.get(f'/api/v1/reports/definitions/{identifier}/run/')
    assert response.status_code == 200
    return response.json()['data']


@pytest.mark.parametrize('aggregation,field,expected', [('count', 'id', 2), ('sum', 'progress', 40), ('avg', 'progress', 20)])
def test_total_metric_is_one_aggregate_not_one_row_per_record(admin_client, admin_user, aggregation, field, expected):
    TaskRecord.objects.create(creator=admin_user, name='first', progress=10)
    TaskRecord.objects.create(creator=admin_user, name='second', progress=30)
    result = run_report(admin_client, definition(dimensions=[], metric={'field': field, 'aggregation': aggregation}))
    assert result['columns'] == ['value']
    assert result['rows'] == [{'value': expected}]


def test_date_dimension_matches_declared_column_and_combines_same_day(admin_client, admin_user):
    for hour in (1, 2):
        task = TaskRecord.objects.create(creator=admin_user, name=f'task-{hour}', task_type='report-day')
        TaskRecord.objects.filter(pk=task.pk).update(created_at=datetime(2026, 1, 2, hour, tzinfo=timezone.utc))
    task = TaskRecord.objects.create(creator=admin_user, name='next-day', task_type='report-day')
    TaskRecord.objects.filter(pk=task.pk).update(created_at=datetime(2026, 1, 3, 1, tzinfo=timezone.utc))
    result = run_report(admin_client, definition(dimensions=[{'field': 'created_at'}, {'field': 'task_type'}]))
    assert result['columns'] == ['created_at', 'task_type', 'value']
    assert result['rows'] == [
        {'created_at': '2026-01-02', 'task_type': 'report-day', 'value': 2},
        {'created_at': '2026-01-03', 'task_type': 'report-day', 'value': 1},
    ]


def reporter(user):
    role = Role.objects.create(name='scoped-reporter')
    UserRole.objects.create(user=user, role=role)
    for action in ('read', 'execute'):
        permission = Permission.objects.create(code=f'report:{action}', name=action, resource='report', action=action)
        RolePermission.objects.create(role=role, permission=permission)
    return role


@pytest.mark.parametrize('source,resource,dimension', [('tasks', 'task', 'status'), ('users', 'user', 'is_active')])
def test_report_aggregate_preserves_source_self_scope(admin_client, admin_user, member_client, member_user, source, resource, dimension):
    role = reporter(member_user)
    DataScopeGrant.objects.create(role=role, resource=resource, scope='self')
    if source == 'tasks':
        TaskRecord.objects.create(creator=admin_user, name='private')
        TaskRecord.objects.create(creator=member_user, name='mine')
    run_report(admin_client, definition(data_source=source, dimensions=[{'field': dimension}]))
    report = ReportDefinition.objects.get(code='aggregate-check')
    result = member_client.get(f'/api/v1/reports/definitions/{report.pk}/run/')
    assert result.status_code == 200
    assert [row['value'] for row in result.json()['data']['rows']] == [1]


def test_file_report_preserves_owner_acl_and_immediate_revocation(admin_client, admin_user, member_client, member_user):
    reporter(member_user)
    for owner, name in [(member_user, 'mine'), (admin_user, 'private'), (admin_user, 'shared')]:
        file = FileModel.objects.create(uploader=owner, original_name=name, file_type='txt', file='fixture.txt')
        if name == 'shared':
            grant = FileAccessGrant.objects.create(file=file, user=member_user, access_level=FileAccessGrant.READ)
    run_report(admin_client, definition(data_source='files', dimensions=[{'field': 'file_type'}]))
    report = ReportDefinition.objects.get(code='aggregate-check')
    path = f'/api/v1/reports/definitions/{report.pk}/run/'
    assert member_client.get(path).json()['data']['rows'] == [{'file_type': 'txt', 'value': 2}]
    grant.is_active = False
    grant.save(update_fields=['is_active'])
    assert member_client.get(path).json()['data']['rows'] == [{'file_type': 'txt', 'value': 1}]
