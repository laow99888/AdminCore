"""业务字段授权公共接缝：真实角色登记，覆盖投影、明细替换与查询旁路。"""
from types import SimpleNamespace

import pytest
from django.http import QueryDict
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.codegen.runtime import (GeneratedSerializerMixin, GeneratedListSerializer, GeneratedViewMixin,
                                      redact_generated_data, enforce_business_write)
from apps.core.contracts import Module
from apps.permissions.models import Role, UserRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def policy(member_user, monkeypatch):
    from apps.core import modules
    declaration = Module('orders', '订单', 'orders', 'apps.orders.urls', ('/orders',),
        data_resources=(('orders', '订单'),), field_policies=(('orders', ('code', 'cost', 'supplier', 'lines',
            'lines.product', 'lines.price', 'parent')),))
    monkeypatch.setattr(modules, 'MODULES', (*modules.MODULES, declaration))
    role = Role.objects.create(name='business-field-contract', field_permissions={'orders': {
        'read': ['code', 'lines', 'lines.product'], 'write': ['code', 'lines', 'lines.product']}})
    UserRole.objects.create(user=member_user, role=role)
    return member_user, role


def test_response_projection_removes_hidden_nested_values_and_labels_without_mutating_input(policy):
    user, _ = policy
    schema = {'module': 'orders', 'structure': 'tree', 'fields': [{'name': key} for key in ('code', 'cost', 'supplier')],
        'details': [{'name': 'lines', 'fields': [{'name': 'product'}, {'name': 'price'}]}]}
    data = {'id': 'record-id', 'version': 3, 'parent': 'parent-id', 'code': 'PO-1', 'cost': '99.99', 'supplier': 'supplier-id',
        'display_labels': {'code': 'visible label', 'supplier': 'hidden name'},
        'lines': [{'id': 'line-id', 'product': 'desk', 'price': '99.99', 'display_labels': {'price': 'hidden cost'}}]}
    result = redact_generated_data(data, schema, user)
    assert result == {'id': 'record-id', 'version': 3, 'code': 'PO-1', 'display_labels': {'code': 'visible label'},
                      'lines': [{'id': 'line-id', 'product': 'desk', 'display_labels': {}}]}
    assert data['cost'] == '99.99' and data['lines'][0]['price'] == '99.99'
    assert redact_generated_data(data, {**schema, 'module': 'legacy'}, user) is data


def test_whole_detail_replace_requires_all_child_fields_but_omission_preserves_group(policy):
    user, role = policy
    schema = {'module': 'orders', 'fields': [{'name': 'code', 'kind': 'string'}, {'name': 'supplier', 'kind': 'relation'}],
              'details': [{'name': 'lines', 'fields': [{'name': 'product'}, {'name': 'price'}]}]}
    enforce_business_write(user, schema, {'version': 3, 'code': 'editable'})
    for values in ({'lines': []}, {'supplier_id': 'reference'}, {'parent_id': 'parent'}):
        with pytest.raises(PermissionDenied):
            enforce_business_write(user, schema, values)
    role.field_permissions['orders']['write'].append('lines.price'); role.save()
    enforce_business_write(user, schema, {'lines': []})


class FieldsSerializer(GeneratedSerializerMixin, serializers.Serializer):
    field_resource = 'orders'
    field_spec = [{'name': 'code', 'kind': 'string', 'form': True}, {'name': 'cost', 'kind': 'decimal', 'form': True},
                  {'name': 'supplier', 'kind': 'relation', 'form': True}]
    detail_spec = []
    is_detail = False
    code = serializers.CharField(required=False)
    cost = serializers.CharField(required=False)
    supplier = serializers.CharField(required=False, allow_null=True)
    version = serializers.IntegerField()
    display_labels = serializers.SerializerMethodField()

    class Meta:
        model = SimpleNamespace(_meta=SimpleNamespace(app_label='orders'))
        list_serializer_class = GeneratedListSerializer


def test_serializer_guards_raw_fields_and_does_not_resolve_hidden_reference_labels(policy, monkeypatch):
    user, _ = policy
    monkeypatch.setattr('apps.core.codegen.runtime.reference_queryset', lambda *args: pytest.fail('hidden label must not query references'))
    request = SimpleNamespace(user=user)
    row = SimpleNamespace(code='visible', cost='hidden', supplier=None, supplier_id=None, version=3)
    serializer = FieldsSerializer([row, row], many=True, context={'request': request})
    assert serializer.data == [{'code': 'visible', 'version': 3, 'display_labels': {}}, {'code': 'visible', 'version': 3, 'display_labels': {}}]
    writable = FieldsSerializer(data={'version': 3, 'code': 'change'}, context={'request': request})
    assert writable.is_valid(), writable.errors
    for values in ({'version': 3, 'cost': '10'}, {'version': 3, 'unknown': 1}):
        with pytest.raises((PermissionDenied, serializers.ValidationError)):
            FieldsSerializer(data=values, context={'request': request}).is_valid(raise_exception=True)
    assert not FieldsSerializer(data={'code': 'missing version'}, context={'request': request}).is_valid()


class ResponseParent:
    def list(self, request, *args, **kwargs):
        return Response({'data': {'items': []}})

    def finalize_response(self, request, response, *args, **kwargs):
        return response

    def filter_queryset(self, queryset):
        return queryset


class ContractView(GeneratedViewMixin, ResponseParent):
    action = 'list'
    generated_schema = {'module': 'orders', 'structure': 'single', 'fields': [
        {'name': 'code', 'kind': 'string', 'query': 'contains'}, {'name': 'cost', 'kind': 'decimal', 'query': 'range'}], 'details': []}
    ordering = ['cost']
    search_fields = ['cost']


def test_view_policy_metadata_query_rejection_and_replay_redaction(policy):
    user, _ = policy
    view = ContractView(); request = SimpleNamespace(user=user, query_params=QueryDict(''))
    view.request = request
    assert view.list(request).data['data']['field_permissions']['read'] == ['code', 'lines', 'lines.product']
    replay = Response({'data': {'id': 'id', 'version': 1, 'code': 'PO', 'cost': 'hidden'}})
    assert 'cost' not in view.finalize_response(request, replay).data['data']
    for query in ('cost_min=0', 'ordering=-cost', 'search=hidden', 'parent=secret'):
        request.query_params = QueryDict(query)
        with pytest.raises(PermissionDenied):
            view.filter_queryset(None)
    request.query_params = QueryDict('')
    class Query:
        def order_by(self, *fields):
            assert fields == ('-created_at', '-id')
            return self
    assert view.filter_queryset(Query()) is not None


def test_frozen_approval_snapshot_is_projected_for_viewer_and_closes_when_module_is_unavailable(policy, monkeypatch):
    from apps.core.codegen import integrations
    from apps.permissions.models import Permission, RolePermission
    from rest_framework.exceptions import NotFound
    user, role = policy
    permission = Permission.objects.create(code='orders:read', resource='orders', action='read', name='读订单')
    RolePermission.objects.create(role=role, permission=permission)
    schema = {'module': 'orders', 'title': '订单', 'approval': {'title_field': 'code'}, 'fields': [
        {'name': 'code', 'label': '编码'}, {'name': 'cost', 'label': '成本'}], 'details': [
        {'name': 'lines', 'label': '明细', 'fields': [{'name': 'product', 'label': '商品'}, {'name': 'price', 'label': '单价'}]}]}
    monkeypatch.setattr(integrations, 'registered_module', lambda key: (schema, None, None))
    monkeypatch.setattr(integrations, 'module_enabled', lambda key: True)
    application = SimpleNamespace(business_module='orders', business_record_id='record-id')
    data = {'title': '订单：record-id', 'extra_data': {'cost': '99.99'}, 'business_snapshot': {
        'fields': {'编码 (code)': 'PO-1', '成本 (cost)': '99.99'},
        'details': {'明细 (lines)': [{'商品 (product)': 'desk', '单价 (price)': '99.99'}]}}}
    projected = integrations.redact_approval_snapshot(application, user, data)
    assert projected['title'] == '订单：PO-1' and projected['extra_data'] == {}
    assert '99.99' not in str(projected)
    assert '99.99' in str(data)
    monkeypatch.setattr(integrations, 'module_enabled', lambda key: False)
    closed = integrations.redact_approval_snapshot(application, user, data)
    assert closed['title'] == '订单' and closed['business_snapshot'] == {'fields': {}, 'details': {}}
    schema['approval'] = None
    assert integrations.redact_approval_snapshot(application, user, data)['business_snapshot'] == {}
    def unavailable(key):
        raise NotFound()
    monkeypatch.setattr(integrations, 'registered_module', unavailable)
    assert integrations.redact_approval_snapshot(application, user, data)['extra_data'] == {}


def test_replayed_labels_are_rebuilt_in_batches_without_changing_business_values(policy, monkeypatch):
    from apps.core.codegen import runtime
    user, _ = policy
    lookups = []
    class Query:
        def filter(self, **values):
            lookups.append(values['pk__in'])
            return self
        def values(self, *names):
            return [{'pk': 'visible', 'name': 'current label'}]
    def reference(field, actor):
        if field['name'] == 'attachment':
            raise PermissionDenied()
        return Query(), 'name'
    monkeypatch.setattr(runtime, 'reference_queryset', reference)
    monkeypatch.setattr(runtime, 'dictionary_options', lambda field: [{'value': 'active', 'label': 'current dictionary'}])
    fields = [{'name': 'supplier', 'kind': 'relation'}, {'name': 'attachment', 'kind': 'file'},
              {'name': 'status', 'kind': 'dictionary'}, {'name': 'code', 'kind': 'string'}]
    schema = {'fields': fields, 'details': [{'name': 'lines', 'fields': fields}]}
    data = {'code': 'original code', 'supplier': 'visible', 'attachment': 'old file', 'status': 'active',
            'display_labels': {'supplier': 'cached name', 'attachment': 'private file'},
            'lines': [{'supplier': 'visible', 'display_labels': {'supplier': 'old'}},
                      {'supplier': 'outside-scope', 'attachment': None, 'display_labels': {'supplier': 'private'}}]}
    refreshed = runtime.refresh_replayed_labels(data, schema, user)
    assert refreshed['code'] == 'original code'
    assert refreshed['display_labels'] == {'supplier': 'current label', 'attachment': '', 'status': 'current dictionary'}
    assert refreshed['lines'][1]['display_labels']['supplier'] == ''
    assert refreshed['lines'][1]['display_labels']['attachment'] == ''
    assert lookups == [{'visible'}, {'visible', 'outside-scope'}]
    assert data['lines'][1]['display_labels']['supplier'] == 'private'


def test_historical_business_titles_cannot_leak_via_approval_search_or_new_notices(member_client, member_user, monkeypatch):
    from uuid import uuid4
    from apps.approvals.models import ApprovalRequest
    from apps.approvals.views import ApprovalRequestViewSet
    application = ApprovalRequest.objects.create(title='业务秘密编码-81572', request_type='other',
        applicant=member_user, assignee=member_user, business_module='orders', business_record_id=uuid4())
    response = member_client.get('/api/v1/approvals/', {'search': application.title})
    assert response.status_code == 200 and response.json()['data']['pagination']['total'] == 0
    ApprovalRequest.objects.create(title='普通报销单-81572', request_type='other', applicant=member_user, assignee=member_user)
    response = member_client.get('/api/v1/approvals/', {'search': '普通报销单-81572'})
    assert response.status_code == 200 and response.json()['data']['pagination']['total'] == 1
    events = []
    monkeypatch.setattr('apps.approvals.views.enqueue_event', lambda **values: events.append(values))
    view = ApprovalRequestViewSet(); view.request = SimpleNamespace(user=member_user)
    view._notice(application, [member_user.pk], 'test', '待审批：' + application.title)
    assert application.title not in events[0]['payload']['title']
    assert str(application.business_record_id) in events[0]['payload']['title']
