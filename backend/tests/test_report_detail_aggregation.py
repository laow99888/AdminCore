"""Run with the real generated procurement fixture; ordinary base tests skip this file."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError

pytest.importorskip('apps.cg_orders.models')
from apps.cg_orders.models import PurchaseLine, PurchaseOrder  # noqa: E402
from apps.cg_suppliers.models import Supplier  # noqa: E402
from apps.core.models import Tenant  # noqa: E402
from apps.core.tenancy import tenant_context  # noqa: E402
from apps.permissions.models import Permission, Role, RolePermission, UserRole  # noqa: E402
from apps.reports.services import catalog_for, drill_down, execute_definition  # noqa: E402
from apps.reports.validators import validate_definition  # noqa: E402

pytestmark = pytest.mark.django_db


def definition(**overrides):
    value = {'data_source': 'cg_orders', 'chart_type': 'table', 'dimensions': [{'field': 'category'}],
             'metrics': [{'key': 'm_orders', 'label': '单数', 'field': 'id', 'aggregation': 'count'},
                         {'key': 'm_total', 'label': '主金额', 'field': 'amount', 'aggregation': 'sum'},
                         {'key': 'm_quantity', 'label': '明细数量', 'field': 'lines.quantity', 'aggregation': 'sum'},
                         {'key': 'm_price', 'label': '明细均价', 'field': 'lines.price', 'aggregation': 'avg'}],
             'filters': [], 'limit': 100}
    return {**value, **overrides}


def order(user, code, amount, quantities=(1,), prices=('1.00',), category='goods', tenant=None):
    supplier, _ = Supplier.objects.get_or_create(code='s-' + (tenant.pk.hex if tenant else 'global'),
                                               defaults={'name': 'Supplier', 'creator': user, 'tenant': tenant})
    row = PurchaseOrder.objects.create(code=code, amount=amount, category=category, supplier=supplier, creator=user, tenant=tenant)
    for index, (quantity, price) in enumerate(zip(quantities, prices)):
        PurchaseLine.objects.create(parent=row, product='item', quantity=quantity, price=price, position=index, tenant=tenant)
    return row


def test_separate_real_sql_prevents_parent_fanout_and_weighted_average(admin_user):
    first = order(admin_user, 'one', '100.00', (2, 3), ('10.00', '20.00'))
    order(admin_user, 'two', '200.00', (4,), ('90.00',))
    order(admin_user, 'empty', '50.00', (), ())
    with CaptureQueriesContext(connection) as captured:
        result = execute_definition(admin_user, definition())
    row = result['rows'][0]
    assert row['category'] == 'goods' and row['m_orders'] == 3 and Decimal(row['m_total']) == Decimal('350.00')
    assert row['m_quantity'] == 9 and abs(Decimal(row['m_price']) - Decimal('40')) < Decimal('0.000001')
    aggregates = [item['sql'] for item in captured if 'm_orders' in item['sql'] or 'm_quantity' in item['sql']]
    assert len(aggregates) == 2, aggregates
    assert 'cg_orders_purchaseline' not in aggregates[0]
    details = drill_down(admin_user, definition(), {'category': 'goods'})
    assert len(details['rows']) == 3 and all('lines.quantity' not in row for row in details['rows'])
    mine = next(row for row in details['rows'] if row['id'] == first.pk)
    assert mine['m_quantity'] == 5 and Decimal(mine['m_price']) == Decimal('15')
    assert Decimal(mine['amount']) == Decimal('100')


def test_detail_only_reports_date_buckets_and_empty_parent_groups(admin_user):
    row = order(admin_user, 'one', '100.00', (2, 3), ('10', '20'))
    order(admin_user, 'empty', '200.00', (), (), category='empty')
    value = definition(metrics=definition()['metrics'][2:])
    result = execute_definition(admin_user, value)
    assert result['rows'][0] == {'category': 'empty', 'm_quantity': None, 'm_price': None}
    assert result['rows'][1]['m_quantity'] == 5
    PurchaseOrder.objects.filter(pk=row.pk).update(created_at=datetime(2026, 1, 5, 12, tzinfo=timezone.utc))
    date_query = definition(dimensions=[{'field': 'created_at', 'grain': 'month'}], filters=[{'field': 'category', 'operator': 'eq', 'value': 'goods'}])
    assert execute_definition(admin_user, date_query)['rows'][0]['m_quantity'] == 5


@pytest.mark.parametrize('fields,key', [(['value'], 'm_value'), (['value', 'm_value'], 'm_value_2')])
def test_legacy_metric_output_preserves_colliding_business_dimensions(admin_user, fields, key):
    first = order(admin_user, 'alias-one', '10', (2,), ('3',))
    second = order(admin_user, 'alias-two', '20', (4,), ('5',))
    PurchaseOrder.objects.filter(pk__in=[first.pk, second.pk]).update(value='business value', m_value='second dimension')
    value = definition(dimensions=[{'field': field} for field in fields])
    del value['metrics']
    value['metric'] = {'field': 'id', 'aggregation': 'count'}
    result = execute_definition(admin_user, value)
    assert result['columns'] == [*fields, key]
    assert result['chart_columns'] == [key]
    assert result['rows'] == [{**{field: 'business value' if field == 'value' else 'second dimension'
                                for field in fields}, key: 2}]
    group = {field: result['rows'][0][field] for field in fields}
    assert len(drill_down(admin_user, value, group)['rows']) == 2
    value['comparison'] = {'field': 'created_at', 'mode': 'previous_period', 'start': '2026-03-01', 'end': '2026-03-03'}
    PurchaseOrder.objects.filter(pk=first.pk).update(created_at=datetime(2026, 3, 1, 12, tzinfo=timezone.utc))
    PurchaseOrder.objects.filter(pk=second.pk).update(created_at=datetime(2026, 2, 27, 12, tzinfo=timezone.utc))
    compared = execute_definition(admin_user, value)
    assert compared['rows'][0][key] == compared['rows'][0][key + '_previous'] == 1
    assert compared['rows'][0]['value'] == 'business value'


def test_legacy_without_comparison_keeps_value_key_for_suffix_dimension(admin_user):
    row = order(admin_user, 'legacy-rate', '10')
    PurchaseOrder.objects.filter(pk=row.pk).update(value_rate='business rate')
    value = definition(dimensions=[{'field': 'value_rate'}])
    del value['metrics']
    value['metric'] = {'field': 'id', 'aggregation': 'count'}
    result = execute_definition(admin_user, value)
    assert result['columns'] == ['value_rate', 'value']
    assert result['chart_columns'] == ['value']
    assert result['rows'] == [{'value_rate': 'business rate', 'value': 1}]
    value['comparison'] = {'field': 'created_at', 'mode': 'previous_period', 'start': '2026-03-01', 'end': '2026-03-03'}
    PurchaseOrder.objects.filter(pk=row.pk).update(created_at=datetime(2026, 3, 1, 12, tzinfo=timezone.utc))
    compared = execute_definition(admin_user, value)
    assert compared['rows'][0]['value_rate'] == 'business rate'
    assert compared['rows'][0]['m_value'] == 1


def test_date_and_child_aliases_skip_unselected_real_generated_fields(admin_user):
    first = order(admin_user, 'date-alias-one', '10', (2, 3), ('3', '4'))
    second = order(admin_user, 'date-alias-two', '20', (4,), ('5',))
    PurchaseOrder.objects.filter(pk__in=[first.pk, second.pk]).update(created_at=datetime(2026, 1, 5, 12, tzinfo=timezone.utc))
    value = definition(dimensions=[{'field': 'created_at', 'grain': 'month'}], metrics=[
        {'key': 'm_count', 'label': '单数', 'field': 'id', 'aggregation': 'count'},
        {'key': 'm_orders', 'label': '明细数', 'field': 'lines.quantity', 'aggregation': 'sum'},
    ])
    result = execute_definition(admin_user, value)
    assert result['rows'][0]['created_at'].isoformat() == '2026-01-01'
    assert result['rows'][0]['m_count'] == 2 and result['rows'][0]['m_orders'] == 9
    assert len(drill_down(admin_user, value, {'created_at': '2026-01-01'})['rows']) == 2
    # Non-date child grouping must also avoid the child model's own valid field.
    value['dimensions'] = [{'field': 'category'}]
    assert execute_definition(admin_user, value)['rows'] == [{'category': 'goods', 'm_count': 2, 'm_orders': 9}]


def test_parent_scope_section_and_child_field_revocation(member_user, admin_user):
    role = Role.objects.create(name='report reader', field_permissions={'cg_orders': {'read': ['category', 'amount', 'lines', 'lines.quantity', 'lines.price']}})
    UserRole.objects.create(user=member_user, role=role)
    permission, _ = Permission.objects.get_or_create(code='cg_orders:read', defaults={'resource': 'cg_orders', 'action': 'read', 'name': 'read'})
    RolePermission.objects.create(role=role, permission=permission)
    mine = order(member_user, 'mine', '10', (2,), ('3',))
    order(admin_user, 'private', '999', (999,), ('999',))
    assert execute_definition(member_user, definition())['rows'][0]['m_quantity'] == 2
    assert len(drill_down(member_user, definition(), {'category': 'goods'})['rows']) == 1
    policy = role.field_permissions
    policy['cg_orders']['read'].remove('lines')
    Role.objects.filter(pk=role.pk).update(field_permissions=policy)
    source = next(item for item in catalog_for(member_user) if item['key'] == 'cg_orders')
    assert 'lines.quantity' not in source['metrics']
    for function in (lambda: execute_definition(member_user, definition()),
                     lambda: drill_down(member_user, definition(), {'category': 'goods'})):
        with pytest.raises(PermissionError):
            function()
    assert PurchaseLine.objects.get(parent=mine).quantity == 2


def test_cross_tenant_children_never_enter_aggregates_or_drilldown(admin_user, settings):
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(slug='report-a', name='A')
    second = Tenant.objects.create(slug='report-b', name='B')
    with tenant_context(first.pk):
        row = order(admin_user, 'same', '100', (2,), ('10',), tenant=first)
    with tenant_context(second.pk):
        order(admin_user, 'same', '900', (900,), ('900',), tenant=second)
    # Deliberately inconsistent legacy/raw child must also be excluded without a tenant selection.
    PurchaseLine.all_objects.create(parent=row, product='wrong tenant', quantity=999, price='999', tenant=second)
    with tenant_context(first.pk):
        assert execute_definition(admin_user, definition())['rows'][0]['m_quantity'] == 2
        assert drill_down(admin_user, definition(), {'category': 'goods'})['rows'][0]['m_quantity'] == 2
    with tenant_context(None):
        assert execute_definition(admin_user, definition(dimensions=[]))['rows'][0]['m_quantity'] == 902


def test_comparison_detail_aggregates_and_parent_totals_keep_same_scope(admin_user):
    now = order(admin_user, 'now', '100', (2, 3), ('10', '20'))
    before = order(admin_user, 'before', '40', (1,), ('10',))
    PurchaseOrder.objects.filter(pk=now.pk).update(created_at=datetime(2026, 3, 1, 12, tzinfo=timezone.utc))
    PurchaseOrder.objects.filter(pk=before.pk).update(created_at=datetime(2026, 2, 27, 12, tzinfo=timezone.utc))
    value = definition(comparison={'field': 'created_at', 'mode': 'previous_period', 'start': '2026-03-01', 'end': '2026-03-03'})
    result = execute_definition(admin_user, value)['rows'][0]
    assert Decimal(result['m_total_delta']) == Decimal('60') and result['m_quantity_rate'] == '400.0000'
    details = drill_down(admin_user, value, {'category': 'goods'})
    assert len(details['rows']) == 1 and details['rows'][0]['id'] == now.pk


@pytest.mark.parametrize('field', ['lines__quantity', 'supplier.amount', 'lines.product', 'notes.content', 'lines.evidence', 'lines.id'])
def test_relation_traversals_and_non_numeric_details_are_not_registered(field):
    value = definition()
    value['metrics'][2]['field'] = field
    with pytest.raises(ValidationError):
        validate_definition(value)


@pytest.mark.django_db
@pytest.mark.parametrize('dimensions,key', [([], 'value'), (['value'], 'm_value')])
def test_legacy_child_aggregate_drilldown_avoids_model_alias_conflict(admin_user, dimensions, key):
    row = order(admin_user, 'audit-legacy-child-' + key, '10', (2, 3), ('1', '2'))
    PurchaseOrder.objects.filter(pk=row.pk).update(value='dimension')
    definition = {'data_source': 'cg_orders', 'chart_type': 'table',
                  'dimensions': [{'field': field} for field in dimensions],
                  'metric': {'field': 'lines.quantity', 'aggregation': 'sum'}, 'filters': [], 'limit': 100}
    aggregate = execute_definition(admin_user, definition)
    assert aggregate['rows'][0][key] == 5
    details = drill_down(admin_user, definition, {field: 'dimension' for field in dimensions})
    assert details['rows'][0][key] == 5
    assert details['rows'][0]['id'] == row.pk
