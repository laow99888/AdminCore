"""标准列表输入、排序和分页的资源边界；不替代真实 PostgreSQL 验收。"""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.urls import URLResolver, get_resolver
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.core.list_queries import stable_ordering, validate_list_query
from apps.core.query_budget import QueryBudgetListMixin
from apps.users.views import UserViewSet

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('query', [
    'unknown=1', 'Search=x', 'page=1&page=2', 'search=a&search=b',
    'is_active=true&is_active=false', 'ordering=username&ordering=created_at',
    'search=' + 'a' * 201, 'page_size=' + '1' * 201, 'search=%00',
    'ordering=password', 'ordering=username,password', 'ordering=profile__phone',
    'ordering=%3F', 'ordering=username;SELECT+1', 'ordering=username,-username',
    'ordering=created_at,created_at', 'ordering=%2Busername', 'ordering=username,',
    'ordering=created_at,username,login_count,created_at,username,login_count',
])
def test_invalid_list_input_is_rejected_before_resource_queries(admin_user, query):
    client = APIClient()
    client.force_authenticate(admin_user)
    # 先加载 URL 模块，避免把导出装饰器的导入误当成执行资源查询。
    get_resolver().resolve('/api/v1/users/')
    with patch.object(UserViewSet, 'get_queryset', side_effect=AssertionError('不应访问资源查询')), \
            patch('apps.core.query_budget.query_budget', side_effect=AssertionError('不应开启查询预算')):
        response = client.get('/api/v1/users/?' + query)
    assert response.status_code == 400
    assert response.json()['code'] == 400


@pytest.mark.parametrize('query', [
    {'search': '中' * 200}, {'search': ''}, {'ordering': ''},
    {'ordering': '-login_count, username'}, {'is_active': 'true'}, {'format': 'json'},
])
def test_supported_list_inputs_remain_accepted(admin_client, query):
    assert admin_client.get('/api/v1/users/', query).status_code == 200


def test_query_boundaries_do_not_replace_authentication_or_permissions(member_client):
    assert APIClient().get('/api/v1/users/?unknown=1').status_code == 401
    assert member_client.get('/api/v1/users/?unknown=1').status_code == 403
    assert member_client.get('/api/v1/notifications/announcements/manage/?unknown=1').status_code == 403


def test_error_translation_and_existing_renderer_negotiation(admin_client):
    response = admin_client.get('/api/v1/users/?search=a&search=b', HTTP_ACCEPT_LANGUAGE='en')
    assert response.status_code == 400
    assert 'Query parameters must not be repeated.' in str(response.json())
    assert admin_client.get('/api/v1/users/?format=unsupported').status_code == 404


def test_same_value_rows_have_repeatable_disjoint_pages(admin_user):
    user_model = get_user_model()
    ids = [UUID(int=value) for value in [9, 3, 7, 1, 5]]
    user_model.objects.bulk_create([user_model(id=identifier, username=f'tie_{identifier.int}',
        password='!', login_count=7) for identifier in ids])
    user_model.objects.filter(pk__in=ids).update(created_at=timezone.now())
    client = APIClient()
    client.force_authenticate(admin_user)

    def pages(ordering=None):
        result = []
        for page in [1, 2, 3]:
            params = {'search': 'tie_', 'page_size': 2, 'page': page}
            if ordering is not None:
                params['ordering'] = ordering
            response = client.get('/api/v1/users/', params)
            assert response.status_code == 200
            result.extend(row['id'] for row in response.json()['data']['items'])
        return result

    expected = [str(identifier) for identifier in sorted(ids)]
    assert pages() == pages() == expected
    assert pages('-login_count') == expected
    assert pages('username') == expected


@pytest.mark.parametrize('ordering,expected', [
    ((), ('pk',)), (('username',), ('username', 'pk')),
    (('-id',), ('-id',)), (('pk',), ('pk',)),
])
def test_stable_ordering_preserves_explicit_primary_key_direction(ordering, expected):
    queryset = get_user_model().objects.order_by(*ordering)
    assert stable_ordering(queryset).query.order_by == expected


def test_future_module_has_no_implicit_serializer_sorting():
    view = SimpleNamespace(ordering_fields=QueryBudgetListMixin.ordering_fields,
        list_query_choices={}, search_fields=[])
    request = Request(APIRequestFactory().get('/', {'ordering': 'username'}))
    from rest_framework.exceptions import ValidationError
    with pytest.raises(ValidationError):
        validate_list_query(request, view)


def test_five_sort_terms_are_accepted_but_six_are_rejected():
    view = SimpleNamespace(ordering_fields=['a', 'b', 'c', 'd', 'e', 'f'],
        list_query_choices={}, search_fields=[])
    from rest_framework.exceptions import ValidationError
    validate_list_query(Request(APIRequestFactory().get('/', {'ordering': 'a,b,c,d,e'})), view)
    with pytest.raises(ValidationError):
        validate_list_query(Request(APIRequestFactory().get('/', {'ordering': 'a,b,c,d,e,f'})), view)


@pytest.mark.parametrize('path,query', [
    ('notifications/', 'scope=other'), ('notifications/', 'scope=all&scope='),
    ('approvals/', 'box=other'), ('approvals/', 'box=todo&box=sent'),
    ('auth/sessions/', 'ordering=last_seen_at'), ('auth/sessions/', 'search=x'),
    ('auth/online-users/', 'ordering=username'),
])
def test_resource_specific_and_fixed_order_contracts(admin_client, path, query):
    assert admin_client.get('/api/v1/' + path + '?' + query).status_code == 400


def test_notification_all_scope_cannot_expand_member_visibility(admin_client, admin_user, member_client, member_user):
    from apps.notifications.models import Notification
    Notification.objects.create(recipient=admin_user, title='private admin')
    mine = Notification.objects.create(recipient=member_user, title='own member')
    response = member_client.get('/api/v1/notifications/?scope=all&ordering=created_at')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['data']['items']] == [str(mine.pk)]
    assert admin_client.get('/api/v1/notifications/?scope=all').json()['data']['pagination']['total'] == 2


def test_every_routed_standard_list_has_a_finite_explicit_sort_policy_and_documented_errors(admin_user):
    from drf_spectacular.generators import SchemaGenerator
    schema = SchemaGenerator().get_schema(request=None, public=True)
    found = set()

    def visit(patterns):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                visit(pattern.url_patterns)
            else:
                callback = pattern.callback
                if getattr(callback, 'actions', {}).get('get') == 'list':
                    found.add(callback.cls)

    visit(get_resolver().url_patterns)
    assert len(found) >= 24
    for view in found:
        assert issubclass(view, QueryBudgetListMixin), view
        assert isinstance(view.ordering_fields, (tuple, list)), view
        assert all(isinstance(field, str) and field != '__all__' for field in view.ordering_fields), view
        if view.__name__ not in {'PersonalSessionViewSet', 'OnlineUserViewSet'}:
            assert view.ordering_fields, view
    client = APIClient()
    client.force_authenticate(admin_user)
    exercised = set()
    for path in schema['paths']:
        if '{' in path:
            continue
        match = get_resolver().resolve(path)
        if getattr(match.func, 'actions', {}).get('get') != 'list':
            continue
        view = match.func.cls
        assert client.get(path, {'unexpected': '1'}).status_code == 400, path
        # 实际编译和执行每个声明字段，防止拼错关系路径引起生产500。
        for field in view.ordering_fields:
            assert client.get(path, {'ordering': field}).status_code == 200, (path, field)
        exercised.add(view)
    assert exercised == found
    paths = ['/api/v1/users/', '/api/v1/organization/departments/',
             '/api/v1/permissions/menus/', '/api/v1/notifications/', '/api/v1/auth/sessions/']
    for path in paths:
        operation = schema['paths'][path]['get']
        assert set(operation['responses']) >= {'200', '400', '503'}
        params = {param['name']: param for param in operation['parameters']}
        if 'ordering' in params:
            assert params['ordering']['schema']['maxLength'] == 200
            assert '400' in params['ordering']['description']
    for path in ['/api/v1/auth/sessions/', '/api/v1/auth/online-users/']:
        assert 'ordering' not in {param['name'] for param in schema['paths'][path]['get']['parameters']}
    assert {param['name']: param for param in schema['paths']['/api/v1/notifications/']['get']['parameters']}['scope']['schema']['enum'] == ['', 'all']
