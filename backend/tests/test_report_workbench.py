from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from rest_framework.exceptions import ValidationError

from apps.core.models import DataScopeGrant
from apps.permissions.models import Role
from apps.reports.dashboards import validate_design
from apps.reports.models import ReportDefinition
from apps.tasks.models import TaskRecord
from tests.test_reports import definition, reporter

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'reports')
    settings.ROOT_URLCONF = 'tests.reports_urls'


def query(**overrides):
    value = definition()
    del value['metric']
    value['metrics'] = [{'key': 'm_count', 'label': '数量', 'field': 'id', 'aggregation': 'count'},
                        {'key': 'm_progress', 'label': '进度合计', 'field': 'progress', 'aggregation': 'sum'}]
    value.update(overrides)
    return value


def dashboard():
    return {'schema_version': 2, 'widgets': [
        {'key': 'status', 'title': '状态分布', 'span': 6, 'definition': query()},
        {'key': 'total', 'title': '合计', 'span': 6, 'definition': query(dimensions=[])},
    ], 'filters': [{'key': 'kind', 'label': '业务类型', 'operator': 'eq', 'value': 'purchase',
                    'bindings': [{'widget': 'status', 'field': 'task_type'}, {'widget': 'total', 'field': 'task_type'}]}],
        'links': [{'source': 'status', 'source_field': 'status', 'target': 'total', 'target_field': 'status'}]}


def publish(client, design, kind='dashboard'):
    response = client.post('/api/v1/reports/definitions/', {'name': '业务看板', 'code': 'business-board', 'kind': kind, 'definition': design}, format='json')
    assert response.status_code == 201, response.content
    identifier = response.json()['data']['id']
    response = client.post(f'/api/v1/reports/definitions/{identifier}/publish/', {'version': 1}, format='json')
    assert response.status_code == 200, response.content
    return f'/api/v1/reports/definitions/{identifier}/'


def test_dashboard_multiple_metrics_filters_links_and_details(admin_client, admin_user):
    for status, progress, kind in [('success', 10, 'purchase'), ('failed', 20, 'purchase'), ('success', 99, 'other')]:
        TaskRecord.objects.create(creator=admin_user, name='task', status=status, progress=progress, task_type=kind)
    path = publish(admin_client, dashboard())
    result = admin_client.get(path + 'run/')
    assert result.status_code == 200
    assert result['Cache-Control'] == 'private, no-store'
    assert result.json()['data']['widgets'][1]['result']['rows'] == [{'m_count': 2, 'm_progress': 30}]
    options = {'selection': {'widget': 'status', 'field': 'status', 'value': 'success'}}
    linked = admin_client.post(path + 'run/', options, format='json')
    assert linked.status_code == 200, linked.content
    assert linked.json()['data']['widgets'][1]['result']['rows'] == [{'m_count': 1, 'm_progress': 10}]
    details = admin_client.post(path + 'details/', {'widget': 'total', 'options': options, 'group': {}}, format='json')
    assert details.status_code == 200, details.content
    data = details.json()['data']
    assert data['columns'] == ['id', 'progress'] and len(data['rows']) == 1
    assert data['rows'][0]['progress'] == 10 and not data['has_more']
    overridden = admin_client.post(path + 'run/', {'filters': {'kind': 'other'}}, format='json')
    assert overridden.json()['data']['widgets'][1]['result']['rows'] == [{'m_count': 1, 'm_progress': 99}]
    assert ReportDefinition.objects.get().definition['filters'][0]['value'] == 'purchase'


def test_dashboard_filter_cannot_replace_saved_predicate(admin_client, admin_user):
    TaskRecord.objects.create(creator=admin_user, name='private', task_type='private', progress=99)
    design = dashboard()
    design['widgets'][1]['definition']['filters'] = [{'field': 'task_type', 'operator': 'eq', 'value': 'purchase'}]
    path = publish(admin_client, design)
    result = admin_client.post(path + 'run/', {'filters': {'kind': 'private'}}, format='json')
    assert result.json()['data']['widgets'][1]['result']['rows'] == [{'m_count': 0, 'm_progress': None}]


@pytest.mark.parametrize('grain,expected', [('day', 2), ('week', 1), ('month', 1), ('quarter', 1), ('year', 1)])
def test_date_buckets_and_drilldown_agree(admin_client, admin_user, grain, expected):
    for day in (5, 6):
        task = TaskRecord.objects.create(creator=admin_user, name='dated', progress=10)
        TaskRecord.objects.filter(pk=task.pk).update(created_at=datetime(2026, 1, day, 10, tzinfo=timezone.utc))
    path = publish(admin_client, query(dimensions=[{'field': 'created_at', 'grain': grain}]), kind='report')
    result = admin_client.get(path + 'run/').json()['data']
    assert len(result['rows']) == expected
    detail = admin_client.post(path + 'details/', {'group': {'created_at': result['rows'][0]['created_at']}}, format='json')
    assert detail.status_code == 200, detail.content
    assert len(detail.json()['data']['rows']) == (1 if grain == 'day' else 2)


def test_scope_and_field_revocation_apply_to_all_widgets_and_details(admin_client, admin_user, member_client, member_user):
    role = reporter(member_user)
    DataScopeGrant.objects.create(role=role, resource='task', scope='self')
    TaskRecord.objects.create(creator=admin_user, name='private', task_type='purchase', progress=100)
    TaskRecord.objects.create(creator=member_user, name='mine', task_type='purchase', progress=3)
    path = publish(admin_client, dashboard())
    assert member_client.get(path + 'run/').json()['data']['widgets'][1]['result']['rows'] == [{'m_count': 1, 'm_progress': 3}]
    assert len(member_client.post(path + 'details/', {'widget': 'total'}, format='json').json()['data']['rows']) == 1
    Role.objects.filter(pk=role.pk).update(field_permissions={'tasks': {'read': ['id', 'status', 'task_type']}})
    with patch('apps.reports.services.execute_prepared') as execute:
        assert member_client.get(path + 'run/').status_code == 403
        execute.assert_not_called()
    assert member_client.post(path + 'details/', {'widget': 'total'}, format='json').status_code == 403


@pytest.mark.parametrize('payload', [
    {'filters': {'unknown': 'x'}}, {'filters': []}, {'filters': {'kind': {'sql': 'x'}}},
    {'selection': {'widget': 'total', 'field': 'progress', 'value': 1}},
    {'selection': {'widget': 'status', 'field': 'status', 'value': None}},
    {'selection': {'widget': 'status', 'field': 'status', 'value': ['success']}}, {'sql': 'select 1'}, [],
])
def test_runtime_options_fail_closed(admin_client, payload):
    path = publish(admin_client, dashboard())
    assert admin_client.post(path + 'run/', payload, format='json').status_code == 400


@pytest.mark.parametrize('payload', [
    {'widget': 'missing'}, {'widget': []}, {'widget': 'status', 'group': {'status__contains': 'x'}},
    {'widget': 'status', 'group': {'status': []}}, {'widget': 'total', 'page': 101},
    {'widget': 'total', 'page_size': True}, {'widget': 'total', 'fields': ['password']},
])
def test_details_fail_closed(admin_client, payload):
    path = publish(admin_client, dashboard())
    assert admin_client.post(path + 'details/', payload, format='json').status_code == 400


def test_truncation_and_detail_pagination_are_explicit(admin_client, admin_user):
    for index in range(3):
        TaskRecord.objects.create(creator=admin_user, name='many', task_type=str(index), status='success')
    path = publish(admin_client, query(dimensions=[{'field': 'task_type'}], limit=1), kind='report')
    result = admin_client.get(path + 'run/').json()['data']
    assert result['truncated'] and len(result['rows']) == 1
    detail = admin_client.post(path + 'details/', {'group': {'task_type': '0'}, 'page_size': 1}, format='json').json()['data']
    assert len(detail['rows']) == 1 and not detail['has_more']


@pytest.mark.parametrize('change', ['widgets', 'width', 'duplicate', 'metric_key', 'pie', 'grain', 'bindings', 'links', 'type', 'version', 'nested'])
def test_design_constraints(change):
    design = deepcopy(dashboard())
    query_def = design['widgets'][0]['definition']
    if change == 'widgets': design['widgets'] *= 5
    elif change == 'width': design['widgets'][0]['span'] = 7
    elif change == 'duplicate': design['widgets'][1]['key'] = 'status'
    elif change == 'metric_key': query_def['metrics'][0]['key'] = 'status'
    elif change == 'pie': query_def['chart_type'] = 'pie'
    elif change == 'grain': query_def['dimensions'][0]['grain'] = 'month'
    elif change == 'bindings': design['filters'][0]['bindings'][0]['field'] = 'password'
    elif change == 'links': design['links'][0]['source_field'] = 'progress'
    elif change == 'type': design['filters'][0]['bindings'][0] = []
    elif change == 'version': design['schema_version'] = True
    elif change == 'nested': query_def.update(dashboard())
    with pytest.raises(ValidationError): validate_design(design)


def test_dashboard_kind_and_draft_execution_guard(admin_client):
    assert admin_client.post('/api/v1/reports/definitions/', {'name': 'wrong', 'code': 'wrong-kind', 'kind': 'report', 'definition': dashboard()}, format='json').status_code == 400
    response = admin_client.post('/api/v1/reports/definitions/', {'name': 'draft', 'code': 'draft-board', 'kind': 'dashboard', 'definition': dashboard()}, format='json')
    path = '/api/v1/reports/definitions/' + response.json()['data']['id'] + '/'
    assert admin_client.get(path + 'run/').status_code == 409
    assert admin_client.post(path + 'details/', {}, format='json').status_code == 409
