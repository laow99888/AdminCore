"""附件真实生命周期：ACL/租户复核、历史冻结、PROTECT 与并发删除。"""
from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from apps.files.models import FileAccessGrant, FileModel
from apps.files.references import is_referenced
from apps.online_forms.models import OnlineForm, OnlineFormFileReference, OnlineFormRecord
from apps.online_forms.validators import validate_definition, validate_record
from tests.file_permissions import grant_files
from tests.test_online_forms import grant_record_permissions

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.ADMINCORE_MODULES = tuple(set(settings.ADMINCORE_MODULES) | {'online_forms', 'files'})
    settings.ROOT_URLCONF = 'tests.online_forms_urls'


def definition():
    return validate_definition({'schema_version': 2, 'fields': [
        {'key': 'title', 'label': '标题', 'type': 'text'},
        {'key': 'proof', 'label': '附件', 'type': 'file'},
        {'key': 'lines', 'label': '明细', 'type': 'detail', 'fields': [
            {'key': 'proof', 'label': '明细附件', 'type': 'file'}]},
    ]})


def form(user, **extra):
    return OnlineForm.objects.create(name='附件申请', code='attachment-form', status='published',
        definition=definition(), created_by=user, **extra)


def document(user, **extra):
    return FileModel.objects.create(original_name='机密合同.txt', file='online-form-test/contract.txt',
        file_type='txt', size=12, uploader=user, **extra)


def record_url(row=None):
    return '/api/v1/online-forms/attachment-form/records/' + (str(row['id']) + '/' if row else '')


def choices_url():
    return '/api/v1/online-forms/attachment-form/attachments/'


def permissions(user):
    grant_record_permissions(user)
    grant_files(user, 'file:read', 'file:download')


@pytest.mark.parametrize('extra', [{'default': str(uuid4())}, {'max': 5}, {'options': ['a']}, {'computation': {'op': 'sum'}}])
def test_file_definition_rejects_embedded_values_and_dynamic_metadata(extra):
    with pytest.raises(ValidationError):
        validate_definition({'schema_version': 2, 'fields': [{'key': 'proof', 'label': '附件', 'type': 'file', **extra}]})


@pytest.mark.parametrize('value', ['https://example.com/a.pdf', 1, [str(uuid4())], {'id': str(uuid4())}])
def test_attachment_accepts_only_uuid_not_url_or_objects(value):
    with pytest.raises(ValidationError):
        validate_record(definition(), {'proof': value})


def test_file_conditions_only_allow_presence_and_required_fields():
    raw = definition()
    raw['fields'][1]['required'] = True
    with pytest.raises(ValidationError):
        validate_record(raw, {})
    raw['fields'].append({'key': 'reason', 'label': '原因', 'type': 'text', 'visible_when': [
        {'field': 'proof', 'op': 'eq', 'value': str(uuid4())}]})
    with pytest.raises(ValidationError):
        validate_definition(raw)
    raw['fields'][-1]['visible_when'] = [{'field': 'proof', 'op': 'not_empty'}]
    assert validate_definition(raw)['fields'][-1]['visible_when'][0]['op'] == 'not_empty'


def test_create_dedupe_append_history_and_frozen_file_type(admin_user, member_user, member_client, admin_client):
    permissions(member_user)
    first, second = document(member_user), document(admin_user)
    FileAccessGrant.objects.create(file=second, user=member_user)
    source = form(admin_user)
    response = member_client.post(record_url(), {'form_id': str(source.pk), 'data': {
        'proof': str(first.pk), 'lines': [{'proof': str(first.pk)}]}}, format='json')
    assert response.status_code == 201, response.content
    row = response.json()['data']
    assert row['definition_snapshot']['fields'][1]['type'] == 'file'
    assert OnlineFormFileReference.objects.count() == 1 and is_referenced(first)
    assert OnlineFormFileReference.objects.get().first_field_path == 'proof'
    # 同编码新版将 proof 改为普通文本，旧记录仍按旧 file schema 校验和附引用。
    new = admin_client.post(f'/api/v1/online-forms/forms/{source.pk}/new-version/', {'version': 1}, format='json').json()['data']
    changed = deepcopy(new['definition']); changed['fields'][1] = {'key': 'proof', 'label': '说明', 'type': 'text'}
    result = admin_client.patch(f"/api/v1/online-forms/forms/{new['id']}/", {'version': 1, 'definition': changed}, format='json')
    assert result.status_code == 200, result.content
    assert admin_client.post(f"/api/v1/online-forms/forms/{new['id']}/publish/", {}, format='json').status_code == 200
    changed_record = member_client.patch(record_url(row), {'version': 1, 'data': {'proof': str(second.pk)}}, format='json')
    assert changed_record.status_code == 200, changed_record.content
    assert OnlineFormFileReference.objects.count() == 2
    updated = changed_record.json()['data']
    assert updated['definition_snapshot']['fields'][1]['type'] == 'file'
    assert member_client.patch(record_url(row), {'version': 2, 'data': {'title': '移除当前附件'}}, format='json').status_code == 200
    assert OnlineFormFileReference.objects.count() == 2 and is_referenced(first) and is_referenced(second)
    from django.db.models.deletion import ProtectedError
    with pytest.raises(ProtectedError):
        FileModel.all_objects.filter(pk=first.pk).delete()
    from apps.core.models import LifecycleConflict
    with pytest.raises(LifecycleConflict):
        first.soft_delete(actor=member_user)
    assert admin_client.delete(f'/api/v1/files/{first.pk}/').status_code == 409


def test_forbidden_missing_deleted_purpose_and_acl_files_roll_back(admin_user, member_user, member_client):
    permissions(member_user); form(admin_user)
    private = document(admin_user)
    deleted = document(member_user); deleted.soft_delete(actor=member_user)
    avatar = document(member_user, purpose='avatar')
    for identifier in [private.pk, deleted.pk, avatar.pk, uuid4()]:
        response = member_client.post(record_url(), {'data': {'proof': str(identifier)}}, format='json')
        assert response.status_code == 400 and '机密合同' not in response.content.decode(), response.content
    assert not OnlineFormRecord.objects.exists() and not OnlineFormFileReference.objects.exists()


def test_acl_revoked_after_selection_blocks_edit_without_leaking_names(admin_user, member_user, member_client):
    permissions(member_user); source = form(admin_user); file = document(admin_user)
    grant = FileAccessGrant.objects.create(file=file, user=member_user)
    selected = member_client.get(choices_url(), {'form_id': str(source.pk), 'field': 'proof', 'selected': str(file.pk)})
    assert selected.status_code == 200 and selected.json()['data']['selected']['original_name'] == file.original_name
    row = member_client.post(record_url(), {'data': {'proof': str(file.pk)}}, format='json').json()['data']
    grant.is_active = False; grant.save()
    resolution = member_client.get(choices_url(), {'record_id': row['id'], 'field': 'proof', 'selected': str(file.pk), 'resolve': 'true'})
    assert resolution.status_code == 200 and resolution.json()['data']['selected'] is None
    assert file.original_name not in resolution.content.decode() and 'online-form-test' not in resolution.content.decode()
    assert member_client.patch(record_url(row), {'version': 1, 'data': {'proof': str(file.pk)}}, format='json').status_code == 400
    record = OnlineFormRecord.objects.get(pk=row['id']); assert record.version == 1 and record.data['proof'] == str(file.pk)
    # 可以明确移除失权附件；保护引用仍保留。
    assert member_client.patch(record_url(row), {'version': 1, 'data': {}}, format='json').status_code == 200
    assert is_referenced(file)


def test_missing_global_file_read_and_disabled_module_not_bypassed(admin_user, member_user, member_client, settings):
    grant_record_permissions(member_user); source = form(admin_user); file = document(member_user)
    assert member_client.post(record_url(), {'data': {'proof': str(file.pk)}}, format='json').status_code == 403
    assert member_client.get(choices_url(), {'form_id': source.pk, 'field': 'proof'}).status_code == 403
    grant_files(member_user, 'file:read')
    settings.ADMINCORE_MODULES = tuple(key for key in settings.ADMINCORE_MODULES if key != 'files')
    assert member_client.post(record_url(), {'data': {'proof': str(file.pk)}}, format='json').status_code == 403
    assert not OnlineFormRecord.objects.exists()


def test_resolve_readonly_history_cannot_search_or_resolve_unbound_file(admin_user, member_user, member_client):
    permissions(member_user); form(admin_user); file = document(member_user); other = document(member_user)
    row = member_client.post(record_url(), {'data': {'lines': [{'proof': str(file.pk)}]}}, format='json').json()['data']
    from apps.permissions.models import RolePermission
    RolePermission.objects.filter(role__userrole__user=member_user, permission__code='online_form:record_update').delete()
    values = {'record_id': row['id'], 'field': 'lines.0.proof', 'selected': str(file.pk), 'resolve': 'true'}
    assert member_client.get(choices_url(), values).json()['data']['selected']['id'] == str(file.pk)
    assert member_client.get(choices_url(), {**values, 'selected': str(other.pk)}).json()['data']['selected'] is None
    assert member_client.get(choices_url(), {**values, 'field': 'proof'}).json()['data']['selected'] is None
    assert member_client.get(choices_url(), {**values, 'resolve': 'false'}).status_code == 403
    assert member_client.get(choices_url(), {**values, 'record_id': str(uuid4())}).status_code == 404
    assert member_client.get(choices_url(), {**values, 'field': 'title'}).status_code == 400


def test_form_and_record_context_do_not_accept_foreign_owner_or_dynamic_fields(admin_user, member_user, member_client, admin_client):
    permissions(member_user); source = form(admin_user); file = document(admin_user)
    row = admin_client.post(record_url(), {'data': {'proof': str(file.pk)}}, format='json').json()['data']
    assert member_client.get(choices_url(), {'record_id': row['id'], 'field': 'proof', 'resolve': 'true'}).status_code == 404
    assert member_client.get(choices_url(), {'form_id': source.pk, 'field': 'unregistered'}).status_code == 400
    source.status = 'archived'; source.save()
    assert member_client.get(choices_url(), {'form_id': source.pk, 'field': 'proof'}).status_code == 409
    source.status = 'draft'; source.save()
    assert member_client.get(choices_url(), {'form_id': source.pk, 'field': 'proof'}).status_code == 403


def test_tenant_admin_control_plane_never_lists_or_binds_foreign_file(settings, admin_user, admin_client):
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first, second = Tenant.objects.create(slug='forms-attach-a', name='A'), Tenant.objects.create(slug='forms-attach-b', name='B')
    with tenant_context(first.pk):
        source = form(admin_user); own = document(admin_user)
    with tenant_context(second.pk):
        foreign = document(admin_user)
    params = {'form_id': str(source.pk), 'field': 'proof', 'selected': str(foreign.pk)}
    choices = admin_client.get(choices_url(), params)
    assert choices.status_code == 200, choices.content
    assert [item['id'] for item in choices.json()['data']['items']] == [str(own.pk)]
    assert choices.json()['data']['selected'] is None
    assert admin_client.post(record_url(), {'data': {'proof': str(foreign.pk)}}, format='json').status_code == 400
    response = admin_client.post(record_url(), {'data': {'proof': str(own.pk)}}, format='json')
    assert response.status_code == 201, response.content
    assert OnlineFormFileReference.all_objects.get().tenant_id == first.pk
    headers = {'HTTP_X_ADMINCORE_TENANT': str(second.pk)}
    assert admin_client.get(choices_url(), params, **headers).status_code == 404
    assert admin_client.get(choices_url(), {'record_id': response.json()['data']['id'], 'field': 'proof'}, **headers).status_code == 404


def test_preview_checks_file_acl_and_never_creates_reference(admin_user, admin_client):
    file = document(admin_user)
    response = admin_client.post('/api/v1/online-forms/validate/', {'definition': definition(), 'data': {'proof': str(file.pk)}}, format='json')
    assert response.status_code == 200 and not OnlineFormFileReference.objects.exists()
    assert admin_client.post('/api/v1/online-forms/validate/', {'definition': definition(), 'data': {'proof': str(uuid4())}}, format='json').status_code == 400


def test_preview_uses_authorized_form_tenant_in_control_plane(settings, admin_user, admin_client, member_client):
    from apps.core.models import Tenant
    from apps.core.tenancy import tenant_context
    settings.ADMINCORE_MULTI_TENANT_ENABLED = True
    first = Tenant.objects.create(slug='form-preview-a', name='A')
    second = Tenant.objects.create(slug='form-preview-b', name='B')
    with tenant_context(first.pk):
        source, file = form(admin_user), document(admin_user)
    payload = {'form_id': str(source.pk), 'definition': definition(), 'data': {'proof': str(file.pk)}}
    url = '/api/v1/online-forms/validate/'
    # 未选租户的平台管理员以服务端表单确定范围；相同文件不因控制平面而错误归入 tenant=None。
    response = admin_client.post(url, payload, format='json')
    assert response.status_code == 200, response.content
    assert response['Cache-Control'] == 'private, no-store'
    assert admin_client.post(url, payload, format='json', HTTP_X_ADMINCORE_TENANT=str(first.pk)).status_code == 200
    assert admin_client.post(url, payload, format='json', HTTP_X_ADMINCORE_TENANT=str(second.pk)).status_code == 404
    assert member_client.post(url, payload, format='json').status_code == 403
    assert admin_client.post(url, {**payload, 'form_id': str(uuid4())}, format='json').status_code == 404
    assert not OnlineFormRecord.objects.exists() and not OnlineFormFileReference.objects.exists()


def test_stale_record_update_does_not_add_reference(admin_user, member_user, member_client):
    permissions(member_user); form(admin_user)
    first, second = document(member_user), document(member_user)
    row = member_client.post(record_url(), {'data': {'proof': str(first.pk)}}, format='json').json()['data']
    assert member_client.patch(record_url(row), {'version': 1, 'data': {}}, format='json').status_code == 200
    response = member_client.patch(record_url(row), {'version': 1, 'data': {'proof': str(second.pk)}}, format='json')
    assert response.status_code == 409
    assert OnlineFormFileReference.objects.count() == 1 and not is_referenced(second)


@pytest.mark.django_db(transaction=True)
def test_postgres_attachment_reference_wins_against_delete(admin_user, member_user):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import connection, connections, transaction
    from apps.core.models import LifecycleConflict
    from apps.online_forms.attachments import attach_files, validate_files
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实 PostgreSQL 文件行锁')
    permissions(member_user); source = form(admin_user); file = document(member_user)
    reached, deleted = Event(), Event()
    def delete():
        try:
            reached.set()
            try:
                FileModel.objects.get(pk=file.pk).soft_delete(actor=admin_user)
            except LifecycleConflict:
                return 'protected'
            deleted.set(); return 'deleted'
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            files = validate_files(source.definition, {'proof': str(file.pk)}, member_user, None, lock=True)
            pending = pool.submit(delete)
            assert reached.wait(5) and not deleted.wait(0.2)
            row = OnlineFormRecord.objects.create(form=source, owner=member_user, form_version=1, data={'proof': str(file.pk)})
            attach_files(row, files)
        assert pending.result(timeout=10) == 'protected'
    assert is_referenced(file)


@pytest.mark.django_db(transaction=True)
def test_postgres_delete_wins_before_waiting_attachment_commit(admin_user, member_user, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import connection, connections, transaction
    from rest_framework.test import APIClient
    from apps.online_forms import views
    if connection.vendor != 'postgresql':
        pytest.skip('需要真实 PostgreSQL 文件行锁')
    permissions(member_user); form(admin_user); file = document(member_user)
    reached = Event(); original = views.validate_files
    def validate(*args, **kwargs):
        reached.set(); return original(*args, **kwargs)
    monkeypatch.setattr(views, 'validate_files', validate)
    def submit():
        try:
            client = APIClient(); client.force_authenticate(member_user)
            return client.post(record_url(), {'data': {'proof': str(file.pk)}}, format='json').status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            FileModel.objects.get(pk=file.pk).soft_delete(actor=admin_user)
            pending = pool.submit(submit)
            assert reached.wait(5)
        assert pending.result(timeout=10) == 400
    assert not OnlineFormRecord.objects.exists() and not OnlineFormFileReference.objects.exists()
