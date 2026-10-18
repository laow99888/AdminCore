"""受控计算契约：精确金额、声明顺序、明细汇总与真实发布历史。"""
from copy import deepcopy

import pytest
from rest_framework.exceptions import ValidationError

from apps.online_forms.validators import validate_definition, validate_record
from tests.test_online_forms import grant_record_permissions


def amount(key, **extra):
    return {'key': key, 'label': key, 'type': 'decimal', 'required': False, 'scale': 2, **extra}


def binary(op, left=None, right=None):
    return {'op': op, 'operands': [left or {'field': 'price'}, right or {'field': 'quantity'}]}


def spec(fields):
    return validate_definition({'schema_version': 2, 'fields': fields})


@pytest.mark.parametrize('op,left,right,expected', [
    ('add', '0.10', '0.20', '0.30'), ('subtract', '0.10', '0.20', '-0.10'),
    ('multiply', '0.10', '0.20', '0.02'), ('divide', '1.00', '6.00', '0.17'),
    ('divide', '-1.00', '8.00', '-0.13'), ('divide', '1.00', '-8.00', '-0.13'),
    ('multiply', '-0.01', '0.01', '0.00'),
    ('add', '9007199254740991.00', '0.01', '9007199254740991.01'),
])
def test_exact_binary_half_up_and_no_float(op, left, right, expected):
    definition = spec([amount('price'), amount('quantity'), amount('total', computation=binary(op))])
    assert validate_record(definition, {'price': left, 'quantity': right, 'total': '999.99'})['total'] == expected
    assert validate_definition(definition) == definition


def test_chained_calculation_drives_conditions_and_comparison_rules():
    definition = spec([amount('price'), amount('quantity'), amount('total', computation=binary('multiply')),
        amount('discounted', computation=binary('multiply', {'field': 'total'}, {'literal': '0.9'})),
        {'key': 'reason', 'label': '原因', 'type': 'text', 'required_when': [{'field': 'discounted', 'op': 'gte', 'value': '90.00'}]},
    ])
    with pytest.raises(ValidationError) as error:
        validate_record(definition, {'price': '50.00', 'quantity': '2.00'})
    assert 'reason' in error.value.detail
    assert validate_record(definition, {'price': '50.00', 'quantity': '2.00', 'reason': '大额'})['discounted'] == '90.00'
    definition['rules'] = [{'left': 'total', 'right': 'discounted', 'op': 'lte', 'message': '比较仍需执行'}]
    with pytest.raises(ValidationError) as error:
        validate_record(definition, {'price': '50.00', 'quantity': '2.00', 'reason': '大额'})
    assert '比较仍需执行' in str(error.value.detail)


def test_detail_line_calculations_and_total_ignore_tampered_values():
    definition = spec([{'key': 'lines', 'label': '明细', 'type': 'detail', 'fields': [
        amount('price'), amount('quantity'), amount('subtotal', computation=binary('multiply')),
    ]}, amount('grand', computation={'op': 'sum', 'detail': 'lines', 'field': 'subtotal'})])
    result = validate_record(definition, {'lines': [{'price': '0.10', 'quantity': '3.00', 'subtotal': '999'},
        {'price': '1.25', 'quantity': '2.00'}], 'grand': {'script': 'evil'}})
    assert result['lines'][0]['subtotal'] == '0.30'
    assert result['grand'] == '2.80'
    # 来源缺失不补零，避免静默低估业务金额。
    partial = validate_record(definition, {'lines': [{'price': '1.00', 'quantity': '1.00'}, {'price': '2.00'}]})
    assert 'grand' not in partial and 'subtotal' not in partial['lines'][1]
    assert 'grand' not in validate_record(definition, {'lines': []})


def test_hidden_inputs_and_computations_never_supply_stale_values():
    definition = spec([{'key': 'show', 'label': '显示', 'type': 'boolean'},
        amount('price', visible_when=[{'field': 'show', 'op': 'eq', 'value': True}]), amount('quantity'),
        amount('total', computation=binary('multiply')),
    ])
    assert validate_record(definition, {'show': False, 'price': '100', 'quantity': '2.00', 'total': '200.00'}) == {'show': False, 'quantity': '2.00'}
    definition['fields'][3]['required'] = True
    with pytest.raises(ValidationError) as error:
        validate_record(definition, {'show': False, 'quantity': '2.00', 'total': '200.00'})
    assert 'total' in error.value.detail


@pytest.mark.parametrize('computation', [
    'price*quantity', {}, {'op': '__import__', 'operands': []},
    {'op': 'add', 'operands': [{'field': 'total'}, {'literal': '1'}]},
    {'op': 'add', 'operands': [{'field': 'later'}, {'literal': '1'}]},
    {'op': 'add', 'operands': [{'field': 'price', 'literal': '1'}, {'literal': '2'}]},
    {'op': 'add', 'operands': [{'literal': 1}, {'literal': '2'}]},
    {'op': 'add', 'operands': [{'literal': 'NaN'}, {'literal': '2'}]},
    {'op': 'add', 'operands': [{'literal': '1e2'}, {'literal': '2'}]},
    {'op': 'add', 'operands': [{'literal': '1.000000001'}, {'literal': '2'}]},
    {'op': 'add', 'operands': [{'literal': '1234567890123456789'}, {'literal': '2'}]},
    {'op': 'add', 'operands': [{'field': 'price'}, {'literal': '1'}], 'sql': 'select 1'},
    {'op': 'sum', 'detail': 'price', 'field': 'x'},
    {'op': 'sum', 'detail': [], 'field': 'x'},
    {'op': 'sum', 'detail': 'lines', 'field': 'unknown'},
    {'op': [], 'operands': []},
])
def test_invalid_unbounded_or_executable_declarations_rejected(computation):
    with pytest.raises(ValidationError):
        spec([amount('price'), {'key': 'lines', 'label': '明细', 'type': 'detail', 'fields': [amount('line')]},
              amount('total', computation=computation), amount('later')])


@pytest.mark.parametrize('field', [
    amount('total', computation=binary('add'), default='0.00'),
    {'key': 'total', 'label': '总额', 'type': 'text', 'computation': binary('add')},
    {'key': 'total', 'label': '总额', 'type': 'number', 'computation': binary('add')},
])
def test_computation_is_decimal_only_without_default(field):
    with pytest.raises(ValidationError):
        spec([amount('price'), amount('quantity'), field])


@pytest.mark.parametrize('op,left,right,bound', [
    ('divide', '1', '0', None), ('multiply', '9999999999999999.99', '2', None),
    ('add', '1.00', '2.00', '2.00'),
])
def test_calculation_errors_remain_field_errors(op, left, right, bound):
    field = amount('total', computation=binary(op), **({'max': bound} if bound else {}))
    with pytest.raises(ValidationError) as error:
        validate_record(spec([amount('price'), amount('quantity'), field]), {'price': left, 'quantity': right})
    assert 'total' in error.value.detail


@pytest.mark.django_db
def test_real_api_recalculates_and_old_history_keeps_frozen_formula(admin_client, member_client, member_user, settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'online_forms')
    settings.ROOT_URLCONF = 'tests.online_forms_urls'
    grant_record_permissions(member_user)
    definition = spec([amount('price'), amount('quantity'), amount('total', computation=binary('multiply'))])
    base = '/api/v1/online-forms/'
    response = admin_client.post(base + 'forms/', {'name': '金额表单', 'code': 'computed-history', 'definition': definition}, format='json')
    assert response.status_code == 201, response.content
    form = response.json()['data']
    response = admin_client.post(f"{base}forms/{form['id']}/publish/", {'version': form['version']}, format='json')
    form = response.json()['data']
    records = base + 'computed-history/records/'
    response = member_client.post(records, {'form_id': form['id'], 'data': {'price': '0.10', 'quantity': '3', 'total': '999.99'}}, format='json')
    assert response.status_code == 201, response.content
    row = response.json()['data']; assert row['data']['total'] == '0.30'
    response = admin_client.post(f"{base}forms/{form['id']}/new-version/", {'version': form['version']}, format='json')
    draft = response.json()['data']
    changed = deepcopy(definition); changed['fields'][2]['computation'] = binary('add')
    response = admin_client.patch(f"{base}forms/{draft['id']}/", {'version': draft['version'], 'definition': changed}, format='json')
    draft = response.json()['data']
    assert admin_client.post(f"{base}forms/{draft['id']}/publish/", {'version': draft['version']}, format='json').status_code == 200
    response = member_client.patch(records + row['id'] + '/', {'version': row['version'], 'data': {'price': '0.20', 'quantity': '3', 'total': '0.01'}}, format='json')
    assert response.status_code == 200, response.content
    assert response.json()['data']['data']['total'] == '0.60'
    assert response.json()['data']['definition_snapshot'] == definition
    response = member_client.post(records, {'form_id': draft['id'], 'data': {'price': '0.20', 'quantity': '3'}}, format='json')
    assert response.status_code == 201 and response.json()['data']['data']['total'] == '3.20'
    # 试填和提交完全共用服务端复算，不回显客户端伪造结果。
    preview = admin_client.post(base + 'validate/', {'definition': changed, 'data': {'price': '0.20', 'quantity': '3', 'total': '999'}}, format='json')
    assert preview.status_code == 200 and preview.json()['data']['data']['total'] == '3.20'
