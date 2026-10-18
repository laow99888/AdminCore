from copy import deepcopy

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.online_forms.models import OnlineForm, OnlineFormRecord
from tests.test_online_forms import definition, grant_record_permissions

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enable_forms(settings):
    settings.ADMINCORE_MODULES = (*settings.ADMINCORE_MODULES, 'online_forms')
    settings.ROOT_URLCONF = 'tests.online_forms_urls'


def publish_initial(admin_client):
    response = admin_client.post('/api/v1/online-forms/forms/', {
        'name': '费用申请', 'code': 'expense-history', 'definition': definition(),
    }, format='json')
    assert response.status_code == 201, response.content
    form = response.json()['data']
    response = admin_client.post(f"/api/v1/online-forms/forms/{form['id']}/publish/", {'version': form['version']}, format='json')
    assert response.status_code == 200, response.content
    return response.json()['data']


def new_release(admin_client, source):
    response = admin_client.post(f"/api/v1/online-forms/forms/{source['id']}/new-version/", {'version': source['version']}, format='json')
    assert response.status_code == 201, response.content
    return response.json()['data']


def test_release_swap_frozen_history_and_owner_update(admin_client, member_client, member_user):
    grant_record_permissions(member_user)
    original = publish_initial(admin_client)
    base = '/api/v1/online-forms/expense-history/records/'
    body = {'form_id': original['id'], 'data': {'title': '旧记录', 'kind': 'A'}}
    response = member_client.post(base, body, format='json', HTTP_IDEMPOTENCY_KEY='historical-create')
    assert response.status_code == 201, response.content
    record = response.json()['data']
    snapshot = deepcopy(record['definition_snapshot'])
    draft = new_release(admin_client, original)
    assert draft['release_number'] == 2 and draft['version'] == 1
    assert admin_client.get('/api/v1/online-forms/published/expense-history/').json()['data']['id'] == original['id']
    update = admin_client.patch(f"/api/v1/online-forms/forms/{draft['id']}/", {
        'version': draft['version'], 'definition': {'fields': [{'key': 'different', 'label': '新必填', 'type': 'text', 'required': True}]},
    }, format='json')
    assert update.status_code == 200, update.content
    draft['version'] = update.json()['data']['version']
    assert admin_client.post(f"/api/v1/online-forms/forms/{draft['id']}/publish/", {'version': draft['version']}, format='json').status_code == 200
    assert OnlineForm.objects.get(pk=original['id']).status == 'archived'
    assert OnlineForm.objects.filter(code=original['code'], status='published').count() == 1
    historical = member_client.get(f"{base}{record['id']}/")
    assert historical.status_code == 200
    assert historical.json()['data']['definition_snapshot'] == snapshot
    assert historical.json()['data']['release_number'] == 1
    assert member_client.get(base).json()['data']['pagination']['total'] == 1
    assert member_client.get(base + '?release_number=2').json()['data']['pagination']['total'] == 0
    response = member_client.patch(f"{base}{record['id']}/", {'version': 1, 'data': {'title': '旧规则修改', 'kind': 'B'}}, format='json')
    assert response.status_code == 200, response.content
    assert response.json()['data']['definition_snapshot'] == snapshot
    assert member_client.patch(f"{base}{record['id']}/", {'version': 1, 'data': {'title': '冲突', 'kind': 'B'}}, format='json').status_code == 409
    assert member_client.post(base, body, format='json', HTTP_IDEMPOTENCY_KEY='stale-page').status_code == 409
    replay = member_client.post(base, body, format='json', HTTP_IDEMPOTENCY_KEY='historical-create')
    assert replay.status_code == 201 and replay['Idempotency-Replayed'] == 'true'
    assert member_client.post(base, {'form_id': draft['id'], 'data': {'different': '新记录'}}, format='json').status_code == 201
    other = get_user_model().objects.create_user('form-history-other')
    grant_record_permissions(other)
    client = APIClient(); client.force_authenticate(other)
    assert client.get(f"{base}{record['id']}/").status_code == 404
    assert client.patch(f"{base}{record['id']}/", {'version': 2, 'data': {'title': '偷改', 'kind': 'B'}}, format='json').status_code == 404
    # 管理身份也不自动获得他人的独立表单记录。
    assert admin_client.get(f"{base}{record['id']}/").status_code == 404


def test_archive_retains_records_but_stops_new_submission(admin_client, member_client, member_user):
    grant_record_permissions(member_user)
    form = publish_initial(admin_client)
    base = '/api/v1/online-forms/expense-history/records/'
    response = member_client.post(base, {'data': {'title': '存量', 'kind': 'A'}}, format='json')
    record = response.json()['data']
    assert admin_client.post(f"/api/v1/online-forms/forms/{form['id']}/archive/", {'version': form['version']}, format='json').status_code == 200
    assert member_client.get(base).json()['data']['pagination']['total'] == 1
    assert member_client.get(f"{base}{record['id']}/").status_code == 200
    assert member_client.post(base, {'data': {'title': '不允许新建', 'kind': 'A'}}, format='json').status_code == 404
    assert member_client.patch(f"{base}{record['id']}/", {'version': 1, 'data': {'title': '仍可修改', 'kind': 'B'}}, format='json').status_code == 200


def test_series_unique_constraints_conflicts_and_immutable_code(admin_client):
    form = publish_initial(admin_client)
    path = f"/api/v1/online-forms/forms/{form['id']}/new-version/"
    assert admin_client.post(path, {'version': True}, format='json').status_code == 400
    assert admin_client.post(path, {'version': form['version'] + 1}, format='json').status_code == 409
    draft = new_release(admin_client, form)
    assert admin_client.post(path, {'version': form['version']}, format='json').status_code == 409
    assert admin_client.patch(f"/api/v1/online-forms/forms/{draft['id']}/", {'version': 1, 'code': 'renamed'}, format='json').status_code == 400
    duplicate = admin_client.post('/api/v1/online-forms/forms/', {'name': '重复', 'code': form['code'], 'definition': definition()}, format='json')
    assert duplicate.status_code == 400
    original = OnlineForm.objects.get(pk=form['id'])
    for release, state in [(1, 'archived'), (3, 'draft'), (3, 'published')]:
        with pytest.raises(IntegrityError), transaction.atomic():
            OnlineForm.objects.create(code=form['code'], name='冲突', release_number=release, status=state, created_by=original.created_by)


@pytest.mark.parametrize('release', ['0', '-1', 'true', '1.5', '999999999999999999999'])
def test_invalid_release_filter_rejected(member_client, member_user, release):
    grant_record_permissions(member_user)
    assert member_client.get('/api/v1/online-forms/expense-history/records/?release_number=' + release).status_code == 400


def test_record_snapshot_cannot_be_replaced_by_client(admin_client, member_client, member_user):
    grant_record_permissions(member_user)
    form = publish_initial(admin_client)
    base = '/api/v1/online-forms/expense-history/records/'
    response = member_client.post(base, {'data': {'title': '冻结', 'kind': 'A'}, 'definition_snapshot': {'fields': []}}, format='json')
    assert response.status_code == 201
    record = OnlineFormRecord.objects.get(pk=response.json()['data']['id'])
    assert record.definition_snapshot == OnlineForm.objects.get(pk=form['id']).definition

@pytest.mark.django_db(transaction=True)
def test_concurrent_new_release_creates_one_draft(admin_client, admin_user, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import connection, connections
    from apps.online_forms import views
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实 PostgreSQL 行锁')
    source = publish_initial(admin_client)
    second = get_user_model().objects.create_superuser('release-admin-two', password='isolated-test-only')
    barrier = Barrier(2)
    original_lock = views.lock_series
    def lock(code):
        barrier.wait(timeout=10)
        return original_lock(code)
    monkeypatch.setattr(views, 'lock_series', lock)
    def create(user):
        try:
            client = APIClient(); client.force_authenticate(user)
            response = client.post(f"/api/v1/online-forms/forms/{source['id']}/new-version/", {'version': source['version']}, format='json')
            return response.status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(create, admin_user), pool.submit(create, second)
        assert sorted([first.result(timeout=15), second.result(timeout=15)]) == [201, 409]
    assert OnlineForm.objects.filter(code=source['code'], status='draft').count() == 1
    assert list(OnlineForm.objects.filter(code=source['code']).order_by('release_number').values_list('release_number', flat=True)) == [1, 2]


@pytest.mark.django_db(transaction=True)
def test_publish_wins_before_waiting_submission_and_old_page_conflicts(admin_client, member_user, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import connection, connections
    from apps.online_forms import views
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实 PostgreSQL 行锁')
    grant_record_permissions(member_user)
    old = publish_initial(admin_client)
    draft = new_release(admin_client, old)
    reached_lock, validated = Event(), Event()
    original_lock, original_validate = views.lock_series, views.validate_record
    def lock(code):
        reached_lock.set()
        return original_lock(code)
    def validate(*args, **kwargs):
        validated.set()
        return original_validate(*args, **kwargs)
    monkeypatch.setattr(views, 'validate_record', validate)
    def submit():
        try:
            client = APIClient(); client.force_authenticate(member_user)
            return client.post('/api/v1/online-forms/expense-history/records/', {'form_id': old['id'], 'data': {'title': '旧页面', 'kind': 'A'}}, format='json').status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            response = admin_client.post(f"/api/v1/online-forms/forms/{draft['id']}/publish/", {'version': draft['version']}, format='json')
            assert response.status_code == 200, response.content
            monkeypatch.setattr(views, 'lock_series', lock)
            waiting = pool.submit(submit)
            assert reached_lock.wait(10)
            assert not validated.wait(0.25)
        assert waiting.result(timeout=10) == 409
    assert OnlineForm.objects.get(pk=old['id']).status == 'archived'
    assert not OnlineFormRecord.objects.exists()

def test_invalid_new_release_keeps_current_published_version(admin_client):
    source = publish_initial(admin_client)
    draft = new_release(admin_client, source)
    OnlineForm.objects.filter(pk=draft['id']).update(definition={'fields': []})
    response = admin_client.post(f"/api/v1/online-forms/forms/{draft['id']}/publish/", {'version': draft['version']}, format='json')
    assert response.status_code == 400
    assert OnlineForm.objects.get(pk=source['id']).status == 'published'
    assert OnlineForm.objects.get(pk=draft['id']).status == 'draft'


def test_tenant_bound_history_and_control_plane_copy_inherit_source_tenant(settings, admin_client, admin_user):
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(slug='form-first', name='表单第一租户')
    second = Tenant.objects.create(slug='form-second', name='表单第二租户')
    with tenant_context(first.pk):
        own = OnlineForm.objects.create(code='tenant-form-a', name='本租户', status='published', definition=definition(), created_by=admin_user)
        own_record = OnlineFormRecord.objects.create(form=own, owner=admin_user, form_version=1, data={'title': '本租户', 'kind': 'A'})
    with tenant_context(second.pk):
        foreign = OnlineForm.objects.create(code='tenant-form-b', name='外租户', status='published', definition=definition(), created_by=admin_user)
        foreign_record = OnlineFormRecord.objects.create(form=foreign, owner=admin_user, form_version=1, data={'title': '外租户', 'kind': 'A'})
    headers = {'HTTP_X_ADMINCORE_TENANT': str(first.pk)}
    listed = admin_client.get('/api/v1/online-forms/tenant-form-a/records/', **headers)
    assert listed.status_code == 200 and [item['id'] for item in listed.json()['data']['items']] == [str(own_record.pk)]
    assert admin_client.get(f'/api/v1/online-forms/tenant-form-b/records/{foreign_record.pk}/', **headers).status_code == 404
    assert admin_client.patch(f'/api/v1/online-forms/tenant-form-b/records/{foreign_record.pk}/', {'version': 1, 'data': {'title': '跨租户', 'kind': 'A'}}, format='json', **headers).status_code == 404
    assert admin_client.post(f'/api/v1/online-forms/forms/{foreign.pk}/new-version/', {'version': 1}, format='json', **headers).status_code == 404
    assert admin_client.post('/api/v1/online-forms/tenant-form-b/records/', {'data': {'title': '跨租户', 'kind': 'A'}}, format='json', **headers).status_code == 404
    # 允许管理员从未限定租户的控制面操作，但新版本/记录必须继承来源表单的租户。
    response = admin_client.post(f'/api/v1/online-forms/forms/{foreign.pk}/new-version/', {'version': 1}, format='json')
    assert response.status_code == 201, response.content
    assert OnlineForm.all_objects.get(pk=response.json()['data']['id']).tenant_id == second.pk
    response = admin_client.post('/api/v1/online-forms/tenant-form-b/records/', {'form_id': str(foreign.pk), 'data': {'title': '正确继承', 'kind': 'A'}}, format='json')
    assert response.status_code == 201, response.content
    assert OnlineFormRecord.all_objects.get(pk=response.json()['data']['id']).tenant_id == second.pk
