from copy import deepcopy
from datetime import date, datetime, timezone

import pytest
from rest_framework.exceptions import ValidationError

from apps.permissions.models import Role
from apps.reports.comparison import previous_window
from apps.reports.dashboards import prepare
from apps.reports.services import drill_down, execute_definition
from apps.reports.validators import validate_definition
from apps.tasks.models import TaskRecord
from tests.test_reports import reporter

pytestmark = pytest.mark.django_db


def definition(**overrides):
    result = {'data_source': 'tasks', 'chart_type': 'table', 'dimensions': [{'field': 'status'}],
              'metrics': [{'key': 'm_count', 'label': '数量', 'field': 'id', 'aggregation': 'count'},
                          {'key': 'm_progress', 'label': '合计', 'field': 'progress', 'aggregation': 'sum'}],
              'filters': [], 'limit': 100,
              'comparison': {'field': 'created_at', 'mode': 'previous_period', 'start': '2026-03-01', 'end': '2026-03-03'}}
    result.update(overrides)
    return result


def task(user, timestamp, status='success', progress=10):
    row = TaskRecord.objects.create(creator=user, name='comparison', status=status, progress=progress)
    TaskRecord.objects.filter(pk=row.pk).update(created_at=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc))
    return row


def test_half_open_local_dates_previous_window_and_drilldown(admin_user, settings):
    settings.TIME_ZONE = 'Asia/Shanghai'
    # Midnight local boundaries, including exactly start and excluding exactly end.
    mine = task(admin_user, '2026-02-28T16:00:00', progress=30)
    task(admin_user, '2026-03-02T16:00:00', progress=999)
    task(admin_user, '2026-02-26T16:00:00', progress=10)
    task(admin_user, '2026-02-26T15:59:59', progress=888)
    value = execute_definition(admin_user, definition())
    row = value['rows'][0]
    assert row == {'status': 'success', 'm_count': 1, 'm_count_previous': 1, 'm_count_delta': '0', 'm_count_rate': '0.0000',
                   'm_progress': 30, 'm_progress_previous': 10, 'm_progress_delta': '20', 'm_progress_rate': '200.0000'}
    assert value['chart_columns'] == ['m_count', 'm_count_previous', 'm_progress', 'm_progress_previous']
    details = drill_down(admin_user, definition(), {'status': 'success'})
    assert len(details['rows']) == 1 and details['rows'][0]['id'] == mine.pk


def test_missing_groups_zero_baseline_nulls_and_global_limit(admin_user):
    task(admin_user, '2026-03-01T12:00:00', status='success', progress=20)
    task(admin_user, '2026-02-27T12:00:00', status='failed', progress=5)
    value = execute_definition(admin_user, definition())
    assert [row['status'] for row in value['rows']] == ['failed', 'success']
    assert value['rows'][0]['m_count_rate'] == '-100.0000'
    assert value['rows'][1]['m_count_previous'] == 0 and value['rows'][1]['m_count_rate'] is None
    assert value['rows'][0]['m_progress'] is None and value['rows'][0]['m_progress_delta'] is None
    bounded = execute_definition(admin_user, definition(limit=1))
    assert bounded['truncated'] and bounded['rows'] == value['rows'][:1]


def test_previous_year_leap_dates_and_decimal_rate(admin_user):
    assert previous_window(date(2024, 2, 29), date(2024, 3, 1), 'previous_year') == (date(2023, 2, 28), date(2023, 3, 1))
    assert previous_window(date(2024, 2, 28), date(2024, 2, 29), 'previous_year') == (date(2023, 2, 28), date(2023, 3, 1))
    value = definition(dimensions=[])
    value['comparison'].update(mode='previous_year', start='2026-01-01', end='2026-01-02')
    task(admin_user, '2026-01-01T12:00:00', progress=4)
    task(admin_user, '2025-01-01T12:00:00', progress=3)
    assert execute_definition(admin_user, value)['rows'][0]['m_progress_rate'] == '33.3333'


@pytest.mark.parametrize('change', ['extra', 'field', 'mode', 'list_mode', 'start', 'week_date', 'end', 'too_long', 'underflow', 'pie', 'date_dimension', 'fixed_date', 'collision'])
def test_invalid_comparison_is_rejected_before_sql(change):
    value = definition()
    comparison = value['comparison']
    if change == 'extra': comparison['sql'] = 'x'
    elif change == 'field': comparison['field'] = 'creator__date_joined'
    elif change == 'mode': comparison['mode'] = 'custom'
    elif change == 'list_mode': comparison['mode'] = []
    elif change == 'start': comparison['start'] = '2026-02-30'
    elif change == 'week_date': comparison.update(start='2026-W01-1', end='2026-01-01')
    elif change == 'end': comparison['end'] = '2026-01-01'
    elif change == 'too_long': comparison['end'] = '2028-01-01'
    elif change == 'underflow': comparison.update(start='0001-01-01', end='0001-01-02')
    elif change == 'pie': value['chart_type'] = 'pie'; value['metrics'] = value['metrics'][:1]
    elif change == 'date_dimension': value['dimensions'] = [{'field': 'created_at'}]
    elif change == 'fixed_date': value['filters'] = [{'field': 'created_at', 'operator': 'gte', 'value': '2026-03-01'}]
    elif change == 'collision': value['metrics'][1]['key'] = 'm_count_previous'
    with pytest.raises(ValidationError):
        validate_definition(value)


def test_date_field_revocation_and_same_scope_each_period(member_user, admin_user):
    from apps.core.models import DataScopeGrant
    role = reporter(member_user)
    DataScopeGrant.objects.create(role=role, resource='task', scope='self')
    task(member_user, '2026-03-01T12:00:00', progress=4)
    task(member_user, '2026-02-27T12:00:00', progress=2)
    task(admin_user, '2026-03-01T12:00:00', progress=999)
    task(admin_user, '2026-02-27T12:00:00', progress=999)
    assert execute_definition(member_user, definition())['rows'][0]['m_progress_rate'] == '100.0000'
    Role.objects.filter(pk=role.pk).update(field_permissions={'tasks': {'read': ['id', 'status', 'progress']}})
    with pytest.raises(PermissionError):
        execute_definition(member_user, definition())
    with pytest.raises(PermissionError):
        drill_down(member_user, definition(), {'status': 'success'})


def test_dashboard_cannot_constrain_only_current_date(admin_user):
    design = {'schema_version': 2, 'widgets': [{'key': 'a', 'title': 'compare', 'span': 12, 'definition': deepcopy(definition())}],
              'filters': [{'key': 'time', 'label': 'time', 'operator': 'gte', 'value': '2026-01-01',
                           'bindings': [{'widget': 'a', 'field': 'created_at'}]}], 'links': []}
    with pytest.raises(ValidationError):
        prepare(admin_user, design)
