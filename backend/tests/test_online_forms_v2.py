"""V2 配置和运行契约：声明边界、条件求值、嵌套错误及真实 API。"""
import json
from pathlib import Path

import pytest
from rest_framework.exceptions import ValidationError

from apps.online_forms.validators import validate_definition, validate_record
from apps.online_forms.models import OnlineForm, OnlineFormRecord
from tests.test_online_forms import grant_record_permissions


def definition():
    return json.loads((Path(__file__).parents[2] / 'examples/online-forms-v2/travel-request.json').read_text(encoding='utf-8'))


def data():
    return {'title':'出差', 'international':False, 'start':'2026-10-18', 'end':'2026-10-20',
            'budget':'100.00', 'costs':[{'item':'车费', 'amount':'0.10', 'quantity':2}]}


def test_roundtrip_precision_conditions_and_details():
    spec = validate_definition(definition())
    assert validate_definition(spec) == spec
    payload = {**data(), 'passport':'STALE', 'reason':'STALE'}
    result = validate_record(spec, payload)
    assert 'passport' not in result and 'reason' not in result
    assert result['costs'][0]['amount'] == '0.10'
    assert result['international'] is False
    assert result['budget'] == '100.00'


def test_conditions_require_passport_and_amount_reason():
    spec = validate_definition(definition())
    with pytest.raises(ValidationError) as exc:
        validate_record(spec, {**data(),'international':True,'budget':'1000.00'})
    assert {'passport','reason'} <= exc.value.detail.keys()
    valid = {**data(),'international':True,'passport':'PASS123','budget':'1000.00','reason':'客户出差'}
    assert validate_record(spec,valid)['passport'] == 'PASS123'


def test_nested_errors_have_stable_row_and_field_paths():
    spec = validate_definition(definition())
    with pytest.raises(ValidationError) as exc:
        validate_record(spec, {**data(),'costs':[{'item':'车费','amount':'0.123','quantity':0}, {'item':'住宿','amount':'1.00','quantity':1}]})
    assert set(exc.value.detail['costs']['0']) == {'amount','quantity'}


def test_cross_field_validation_and_hidden_comparison_skipping():
    spec = validate_definition(definition())
    with pytest.raises(ValidationError) as exc:
        validate_record(spec, {**data(),'end':'2026-10-17'})
    assert 'start' in exc.value.detail
    simple = validate_definition({'schema_version':2,'fields':[
        {'key':'show','label':'显示','type':'boolean'},
        {'key':'a','label':'A','type':'decimal','visible_when':[{'field':'show','op':'eq','value':True}]},
        {'key':'b','label':'B','type':'decimal'}], 'rules':[{'left':'a','right':'b','op':'lte','message':'A不能大于B'}]})
    assert validate_record(simple, {'show':False,'a':'10.00','b':'1.00'}) == {'show':False,'b':'1.00'}


@pytest.mark.parametrize('field,value', [('budget', 0.1), ('budget','NaN'), ('budget','1e2'), ('budget','0.001'), ('international',1), ('start','2026-02-30'), ('costs',[{'item':'A','amount':'1.00','quantity':1,'extra':1}]), ('costs',[]), ('costs',{}), ('costs',[None])])
def test_invalid_records_rejected(field,value):
    with pytest.raises(ValidationError):
        validate_record(validate_definition(definition()), {**data(),field:value})


@pytest.mark.parametrize('patch', [
    {'schema_version':True}, {'schema_version':3}, {'script':'alert(1)'},
    {'sections':[{'key':'x','title':'X'},{'key':'x','title':'Y'}]},
    {'fields':[{'key':'constructor','label':'X','type':'text'}]},
    {'fields':[{'key':'x','label':'X','type':'text','component':'script'}]},
    {'fields':[{'key':'x','label':'X','type':'text','section':['bad']}]},
    {'fields':[{'key':'x','label':'X','type':'text','visible_when':[{'field':'later','op':'eq','value':'x'}]}]},
    {'fields':[{'key':'x','label':'X','type':'text','visible_when':[{'field':[],'op':'eq','value':'x'}]}]},
    {'fields':[{'key':'x','label':'X','type':'detail','fields':[{'key':'nested','label':'N','type':'detail'}]}]},
    {'fields':[{'key':'x','label':'X','type':'decimal','scale':9}]},
    {'fields':[{'key':'x','label':'X','type':'decimal','min':'2','max':'1'}]},
    {'fields':[{'key':'x','label':'X','type':'text','span':3}]},
    {'rules':[{'left':[],'right':'end','op':'lte','message':'bad'}]},
])
def test_malformed_definitions_fail_with_validation_error(patch):
    with pytest.raises(ValidationError):
        validate_definition({**definition(),**patch})


def test_conditions_strip_hidden_transitive_values_and_use_defaults():
    spec = validate_definition({'schema_version':2,'fields':[
        {'key':'show','label':'显示','type':'boolean','default':False},
        {'key':'middle','label':'中间','type':'text','default':'yes','visible_when':[{'field':'show','op':'eq','value':True}]},
        {'key':'last','label':'末尾','type':'text','required':True,'visible_when':[{'field':'middle','op':'not_empty'}]}]})
    assert validate_record(spec,{'middle':'injected','last':'injected'}) == {'show':False}


def test_multiselect_datetime_and_comparisons():
    spec = validate_definition({'schema_version':2,'fields':[
        {'key':'options','label':'多选','type':'multiselect','options':['A','B'],'default':['B']},
        {'key':'start','label':'开始','type':'datetime'}, {'key':'end','label':'结束','type':'datetime'}],
        'rules':[{'left':'start','right':'end','op':'lt','message':'开始须早于结束'}]})
    assert validate_record(spec,{}) == {'options':['B']}
    with pytest.raises(ValidationError):
        validate_record(spec,{'options':['A','A']})
    with pytest.raises(ValidationError):
        validate_record(spec,{'start':'2026-10-18T12:00:00'})
    assert validate_record(spec,{'start':'2026-10-18T12:00:00+08:00','end':'2026-10-18T05:00:00Z'})


@pytest.mark.parametrize('kind,raw,op,expected,visible', [
    ('number',2,'lt',3,True), ('number',2,'lte',2,True), ('number',2,'gt',3,False), ('number',2,'gte',2,True),
    ('number',2,'eq',2.0,True), ('boolean',False,'ne',True,True), ('number',None,'gte',2,False),
    ('decimal','2.0','in',['1.00','2.00'],True), ('number',2,'in',[1,2.0],True),
    ('decimal','-0.00','eq','0.00',True), ('decimal','-0.00','in',['0.00'],True),
    ('datetime','2026-10-18T12:00:00+08:00','eq','2026-10-18T04:00:00Z',True),
    ('datetime','2026-10-18T12:00:00+08:00','gt','2026-10-18T03:00:00Z',True),
])
def test_typed_condition_operators(kind,raw,op,expected,visible):
    spec=validate_definition({'schema_version':2,'fields':[
        {'key':'source','label':'来源','type':kind},
        {'key':'target','label':'目标','type':'text','default':'shown','visible_when':[{'field':'source','op':op,'value':expected}]}]})
    assert ('target' in validate_record(spec,{'source':raw})) is visible


@pytest.mark.parametrize('field', [
    {'key':'x','label':'','type':'text'}, {'key':'x','label':'X','type':'text','required':1},
    {'key':'x','label':'X','type':'text','min':1}, {'key':'x','label':'X','type':'text','scale':2},
    {'key':'x','label':'X','type':'date','default':'bad'}, {'key':'x','label':'X','type':'datetime','default':5},
    {'key':'x','label':'X','type':'decimal','default':'123456789012345678.12'},
    {'key':'x','label':'X','type':'decimal','max_length':10}, {'key':'x','label':'X','type':'detail','fields':[]},
    {'key':'x','label':'X','type':'detail','fields':[{'key':'n','label':'N','type':'text','section':'x'}]},
    {'key':'x','label':'X','type':'detail','fields':[{'key':'n','label':'N','type':'text'}],'min_rows':101},
    {'key':'x','label':'X','type':'text','visible_when':[]},
])
def test_type_specific_configuration_limits(field):
    with pytest.raises(ValidationError):
        validate_definition({'schema_version':2,'fields':[field]})


def test_definition_and_submission_resource_budgets():
    with pytest.raises(ValidationError):
        validate_definition({'schema_version':2,'fields':[], 'padding':'x'*131073})
    with pytest.raises(ValidationError):
        validate_record(validate_definition(definition()),{**data(),'title':'x'*131073})
    with pytest.raises(ValidationError):
        validate_definition({'schema_version':2,'fields':[{'key':'n','label':'N','type':'number','default':float('nan')}]})
    with pytest.raises(ValidationError):
        validate_record(validate_definition(definition()),{**data(),'costs':[{'item':'A','amount':'1.00','quantity':1}]*21})
    with pytest.raises(ValidationError):
        validate_record(validate_definition(definition()),None)


@pytest.mark.parametrize('condition', [
    {'field':'source','op':'lt','value':'x'}, {'field':'source','op':'empty','value':'x'},
    {'field':'source','op':'in','value':[]}, {'field':'source','op':'eq','value':''},
    {'field':'source','op':'eval','value':'x'}, {'field':'source','op':'eq','value':'x','extra':1},
])
def test_unsafe_or_ambiguous_condition_configuration_rejected(condition):
    with pytest.raises(ValidationError):
        validate_definition({'schema_version':2,'fields':[{'key':'source','label':'S','type':'text'},
            {'key':'target','label':'T','type':'text','visible_when':[condition]}]})


def test_detail_row_comparisons_and_optional_blank_values():
    spec=validate_definition({'schema_version':2,'fields':[
        {'key':'title','label':'标题','type':'text'},
        {'key':'lines','label':'明细','type':'detail','fields':[{'key':'a','label':'A','type':'decimal'},{'key':'b','label':'B','type':'decimal'}],
         'rules':[{'left':'a','right':'b','op':'lte','message':'A不能大于B'}]}]})
    assert validate_record(spec,{'title':'','lines':[]}) == {}
    with pytest.raises(ValidationError) as exc:
        validate_record(spec,{'lines':[{'a':'2.00','b':'1.00'}]})
    assert exc.value.detail['lines']['0']['a'] == 'A不能大于B'


@pytest.fixture
def enabled(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES,'online_forms')
    settings.ROOT_URLCONF='tests.online_forms_urls'


@pytest.mark.django_db
def test_api_preview_save_publish_submit_update_isolation(enabled, admin_client, member_client, member_user):
    grant_record_permissions(member_user)
    preview = admin_client.post('/api/v1/online-forms/validate/',{'definition':definition(),'data':data()},format='json')
    assert preview.status_code == 200 and preview['Cache-Control'] == 'private, no-store'
    assert OnlineForm.objects.count() == OnlineFormRecord.objects.count() == 0
    assert member_client.post('/api/v1/online-forms/validate/',{'definition':definition()},format='json').status_code == 403
    created = admin_client.post('/api/v1/online-forms/forms/',{'name':'出差申请','code':'travel-form','definition':definition()},format='json')
    assert created.status_code == 201,created.json()
    form=created.json()['data']
    assert admin_client.post(f"/api/v1/online-forms/forms/{form['id']}/publish/",{'version':form['version']},format='json').status_code == 200
    base='/api/v1/online-forms/travel-form/records/'
    payload={'data':{**data(),'passport':'HIDDEN'}}
    saved=member_client.post(base,payload,format='json',HTTP_IDEMPOTENCY_KEY='v2-record')
    assert saved.status_code == 201,saved.json()
    record=saved.json()['data']
    assert 'passport' not in record['data'] and record['data']['budget']=='100.00'
    assert member_client.post(base,payload,format='json',HTTP_IDEMPOTENCY_KEY='v2-record')['Idempotency-Replayed']=='true'
    assert OnlineFormRecord.objects.count()==1
    invalid=member_client.patch(base+record['id']+'/',{'version':1,'data':{**data(),'end':'2026-10-17'}},format='json')
    assert invalid.status_code==400
    assert OnlineFormRecord.objects.get().version==1
    updated=member_client.patch(base+record['id']+'/',{'version':1,'data':{**data(),'title':'新标题'}},format='json')
    assert updated.status_code==200 and updated.json()['data']['version']==2
    assert member_client.patch(base+record['id']+'/',{'version':1,'data':data()},format='json').status_code==409
    assert admin_client.get(base+record['id']+'/').status_code==404


@pytest.mark.django_db
def test_publish_revalidates_persisted_definition(enabled, admin_client, admin_user):
    form=OnlineForm.objects.create(code='bad-persisted',name='旧脏数据',definition={'fields':[]},created_by=admin_user)
    assert admin_client.post(f'/api/v1/online-forms/forms/{form.pk}/publish/',format='json').status_code==400
    form.refresh_from_db()
    assert form.status=='draft'


@pytest.mark.django_db
@pytest.mark.parametrize('payload', [[], 'invalid', 1, True, None])
def test_record_api_rejects_non_object_payloads(enabled, member_client, member_user, admin_user, payload):
    grant_record_permissions(member_user)
    form = OnlineForm.objects.create(code='typed-payload', name='请求类型', status='published',
                                    definition=validate_definition(definition()), created_by=admin_user)
    row = OnlineFormRecord.objects.create(form=form, owner=member_user, form_version=form.version, data=data())
    base = '/api/v1/online-forms/typed-payload/records/'
    for method, path in [('POST', base), ('PATCH', base + str(row.pk) + '/')]:
        response = member_client.generic(method, path, json.dumps(payload), content_type='application/json')
        assert response.status_code == 400
    row.refresh_from_db()
    assert row.version == 1 and row.data == data()
    assert OnlineFormRecord.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('version', [True, 1.0, '1', None, 0, -1])
def test_record_update_requires_positive_integer_version(enabled, member_client, member_user, admin_user, version):
    grant_record_permissions(member_user)
    form = OnlineForm.objects.create(code='typed-version', name='版本类型', status='published',
                                    definition=validate_definition(definition()), created_by=admin_user)
    row = OnlineFormRecord.objects.create(form=form, owner=member_user, form_version=form.version, data=data())
    response = member_client.patch(f'/api/v1/online-forms/typed-version/records/{row.pk}/',
                                   {'version': version, 'data': {**data(), 'title': '无效更新'}}, format='json')
    assert response.status_code == 400
    row.refresh_from_db()
    assert row.version == 1 and row.data == data()


@pytest.mark.django_db
def test_preview_rate_is_enforced(enabled, admin_client, monkeypatch):
    from apps.online_forms.views import FormValidationThrottle
    monkeypatch.setattr(FormValidationThrottle, 'rate', '2/min')
    for _ in range(2):
        assert admin_client.post('/api/v1/online-forms/validate/',{'definition':definition()},format='json').status_code==200
    assert admin_client.post('/api/v1/online-forms/validate/',{'definition':definition()},format='json').status_code==429


@pytest.mark.django_db(transaction=True)
def test_archiving_wins_before_waiting_record_submission(enabled, admin_user, member_user, monkeypatch):
    """归档持锁时提交须等待，并在锁释放后重新检查 published 状态。"""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import connection, connections, transaction
    from rest_framework.test import APIClient
    from apps.online_forms import views
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实 PostgreSQL 行锁')
    grant_record_permissions(member_user)
    row=OnlineForm.objects.create(code='archive-race',name='并发归档',status='published',definition=validate_definition(definition()),created_by=admin_user)
    authorized, validated=Event(),Event()
    original_authorize, original_validate=views.authorize_write,views.validate_record
    def authorize(*args,**kwargs):
        actor=original_authorize(*args,**kwargs)
        authorized.set()
        return actor
    def validate(*args,**kwargs):
        validated.set()
        return original_validate(*args,**kwargs)
    monkeypatch.setattr(views,'authorize_write',authorize)
    monkeypatch.setattr(views,'validate_record',validate)
    def submit():
        try:
            client=APIClient();client.force_authenticate(member_user)
            return client.post('/api/v1/online-forms/archive-race/records/',{'data':data()},format='json',HTTP_IDEMPOTENCY_KEY='archive-race').status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            locked=OnlineForm.objects.select_for_update().get(pk=row.pk)
            locked.status='archived';locked.save(update_fields=['status'])
            future=pool.submit(submit)
            assert authorized.wait(10)
            assert not validated.wait(0.5)
        assert future.result(timeout=10)==404
    assert not OnlineFormRecord.objects.filter(form=row).exists()
