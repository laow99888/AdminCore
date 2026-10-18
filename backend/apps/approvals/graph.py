"""V2 有向无环流程：有序条件出口、默认出口与受限人员解析。"""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from uuid import UUID

from django.core.exceptions import ValidationError


def scalar(kind, value):
    valid = False
    if kind == 'text':
        valid = isinstance(value, str) and len(value) <= 200 and '\x00' not in value
    elif kind == 'boolean':
        valid = type(value) is bool
    elif kind == 'integer':
        valid = type(value) is int and -2147483648 <= value <= 2147483647
    elif kind == 'decimal':
        valid = isinstance(value, str) and bool(re.fullmatch(r'-?[0-9]{1,18}(?:\.[0-9]{1,8})?', value))
        if valid:
            try:
                valid = len(Decimal(value).as_tuple().digits) <= 18
            except InvalidOperation:
                valid = False
    elif kind == 'date':
        try:
            valid = isinstance(value, str) and bool(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value)) and bool(date.fromisoformat(value))
        except ValueError:
            valid = False
    if not valid:
        raise ValidationError('流程输入值与登记类型不一致')
    return value


def validate_graph(definition):
    if (set(definition) != {'schema_version', 'inputs', 'nodes', 'edges'}
            or type(definition['schema_version']) is not int or definition['schema_version'] != 2
            or len(json.dumps(definition, ensure_ascii=False).encode()) > 65536):
        raise ValidationError('V2流程定义格式无效或超过64KiB')
    inputs, nodes, edges = definition['inputs'], definition['nodes'], definition['edges']
    if not isinstance(inputs, list) or len(inputs) > 20:
        raise ValidationError('流程输入最多20项')
    fields = {}
    for field in inputs:
        if (not isinstance(field, dict) or set(field) != {'key', 'type'}
                or not isinstance(field['key'], str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,29}', field['key'])
                or field['key'] in fields or field['key'] in {'constructor', 'prototype', '__proto__'}
                or not isinstance(field['type'], str) or field['type'] not in {'text', 'integer', 'decimal', 'boolean', 'date'}):
            raise ValidationError('流程输入必须为唯一标识和受支持类型')
        fields[field['key']] = field['type']
    if not isinstance(nodes, list) or not 3 <= len(nodes) <= 100 or not isinstance(edges, list) or len(edges) > 300:
        raise ValidationError('V2流程节点或连线数量无效')
    kinds, ids = {}, set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) - {'id', 'type', 'name', 'assignee_ids', 'assignee', 'mode', 'timeout'}:
            raise ValidationError('流程节点包含未知字段')
        key, kind = node.get('id'), node.get('type')
        if not isinstance(key, str) or not 1 <= len(key) <= 64 or key in ids:
            raise ValidationError('流程节点标识必须唯一且有效')
        if not isinstance(kind, str) or kind not in {'start', 'end', 'branch', 'user', 'parallel', 'or'}:
            raise ValidationError('流程节点类型不受支持')
        ids.add(key); kinds[key] = kind
        if kind in {'user', 'parallel', 'or'}:
            if 'timeout' in node:
                timeout = node['timeout']
                if (not isinstance(timeout, dict) or set(timeout) - {'minutes', 'escalate_after_minutes', 'escalate_to', 'calendar'}
                        or type(timeout.get('minutes')) is not int or not 1 <= timeout['minutes'] <= 525600
                        or ('escalate_after_minutes' in timeout) != ('escalate_to' in timeout)):
                    raise ValidationError('超时配置必须为1至525600分钟，升级时限和人员必须同时配置')
                if 'calendar' in timeout:
                    from .calendar import validate_calendar
                    validate_calendar(timeout['calendar'])
                if 'escalate_after_minutes' in timeout:
                    if type(timeout['escalate_after_minutes']) is not int or not timeout['minutes'] < timeout['escalate_after_minutes'] <= 525600:
                        raise ValidationError('升级时限必须晚于提醒时限且不超过525600分钟')
                    try:
                        UUID(timeout['escalate_to'])
                    except (ValueError, TypeError, AttributeError):
                        raise ValidationError('超时升级人员标识无效') from None
            mode = node.get('mode', 'any' if kind == 'or' else 'all')
            if not isinstance(mode, str) or mode not in {'all', 'any'}:
                raise ValidationError('审批节点模式只能是 all 或 any')
            if ('assignee' in node) == ('assignee_ids' in node):
                raise ValidationError('审批节点必须选择一种人员来源')
            if 'assignee' in node:
                source = node['assignee']
                if isinstance(source, dict) and source.get('source') == 'department_leader':
                    if set(source) != {'source', 'levels'} or type(source['levels']) is not int or not 1 <= source['levels'] <= 10:
                        raise ValidationError('部门主管层级必须为1至10的整数')
                elif not isinstance(source, dict) or source != {'source': 'applicant'}:
                    if not isinstance(source, dict) or set(source) != {'source', 'role_id'} or source['source'] != 'role':
                        raise ValidationError('动态审批人只支持申请人、角色或部门主管')
                    try:
                        UUID(source['role_id'])
                    except (ValueError, TypeError, AttributeError):
                        raise ValidationError('动态审批角色标识无效') from None
            else:
                users = node['assignee_ids']
                try:
                    if (not isinstance(users, list) or not 1 <= len(users) <= 100
                            or any(not isinstance(value, str) for value in users)
                            or len({UUID(value) for value in users}) != len(users)):
                        raise ValueError
                except (ValueError, TypeError, AttributeError):
                    raise ValidationError('审批人标识无效或重复') from None
        elif set(node) & {'mode', 'assignee', 'assignee_ids', 'timeout'}:
            raise ValidationError('非审批节点不能配置审批人')
    if list(kinds.values()).count('start') != 1 or list(kinds.values()).count('end') != 1:
        raise ValidationError('流程必须且只能包含一个开始节点和一个结束节点')
    adjacency, incoming = {key: [] for key in ids}, {key: 0 for key in ids}
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) - {'from', 'to', 'when', 'default'}:
            raise ValidationError('流程连线包含未知字段')
        source, target = edge.get('from'), edge.get('to')
        if not isinstance(source, str) or not isinstance(target, str) or source not in ids or target not in ids or source == target:
            raise ValidationError('流程连线端点无效')
        adjacency[source].append(edge); incoming[target] += 1
        if kinds[source] == 'branch':
            if ('when' in edge) == ('default' in edge):
                raise ValidationError('分支出口必须配置条件或默认出口')
            if 'default' in edge and edge['default'] is not True:
                raise ValidationError('默认出口必须为 true')
            if 'when' in edge:
                condition = edge['when']
                if (not isinstance(condition, dict) or set(condition) != {'field', 'op', 'value'}
                        or not isinstance(condition['field'], str) or condition['field'] not in fields
                        or not isinstance(condition['op'], str) or condition['op'] not in {'eq', 'ne', 'lt', 'lte', 'gt', 'gte'}
                        or fields[condition['field']] in {'text', 'boolean'} and condition['op'] not in {'eq', 'ne'}):
                    raise ValidationError('分支条件必须引用登记输入与允许的比较操作')
                scalar(fields[condition['field']], condition['value'])
        elif set(edge) != {'from', 'to'}:
            raise ValidationError('仅分支节点可以配置条件出口')
    start = next(key for key in ids if kinds[key] == 'start')
    end = next(key for key in ids if kinds[key] == 'end')
    for key, outgoing in adjacency.items():
        if kinds[key] == 'branch':
            if not 2 <= len(outgoing) <= 20 or sum('default' in edge for edge in outgoing) != 1:
                raise ValidationError('分支需要2至20个出口且恰好一个默认出口')
        elif len(outgoing) != (0 if key == end else 1):
            raise ValidationError('非分支节点必须有唯一出口，结束节点不能有出口')
        if (key == start and incoming[key]) or (key != start and not incoming[key]):
            raise ValidationError('流程节点必须从开始节点可达')
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValidationError('流程连线不能形成环')
        if key in visited:
            return
        visiting.add(key)
        for edge in adjacency[key]:
            visit(edge['to'])
        visiting.remove(key); visited.add(key)
    visit(start)
    if visited != ids:
        raise ValidationError('流程存在从开始节点不可达的节点')
    # 所有可能路径均须先经过至少一个审批节点，避免默认出口直接自动通过。
    unreviewed = set()
    def has_unreviewed_end(key):
        if kinds[key] in {'user', 'parallel', 'or'} or key in unreviewed:
            return False
        unreviewed.add(key)
        return key == end or any(has_unreviewed_end(edge['to']) for edge in adjacency[key])
    if has_unreviewed_end(start):
        raise ValidationError('每条流程路径都必须经过审批节点')
    return definition


def validate_inputs(definition, data):
    if definition.get('schema_version') != 2:
        return data
    fields = {field['key']: field['type'] for field in definition['inputs']}
    if data is None and not fields:
        data = {}
    if not isinstance(data, dict) or set(data) != set(fields):
        raise ValidationError('流程输入必须完整匹配登记字段')
    return {key: scalar(kind, data[key]) for key, kind in fields.items()}


def next_node(definition, current, data):
    outgoing = [edge for edge in definition['edges'] if edge['from'] == current]
    fields = {field['key']: field['type'] for field in definition.get('inputs', [])}
    fallback = None
    for edge in outgoing:
        if edge.get('default'):
            fallback = edge['to']; continue
        condition = edge.get('when')
        if condition is None:
            return edge['to']
        key = condition['field']; left, right = data[key], condition['value']
        if fields[key] == 'decimal':
            left, right = Decimal(left), Decimal(right)
        matched = {'eq': lambda: left == right, 'ne': lambda: left != right,
                   'lt': lambda: left < right, 'lte': lambda: left <= right,
                   'gt': lambda: left > right, 'gte': lambda: left >= right}[condition['op']]()
        if matched:
            return edge['to']
    return fallback


def resolve_assignment(application, node):
    from django.contrib.auth import get_user_model
    from apps.core.tenancy import enabled
    from apps.core.models import TenantMembership
    from rest_framework.exceptions import ValidationError as APIValidationError
    users = get_user_model().objects.filter(is_active=True, is_service_account=False)
    if enabled() and application.tenant_id:
        users = users.filter(pk__in=TenantMembership.objects.filter(
            tenant_id=application.tenant_id, is_active=True, tenant__status='active').values('user_id'))
    source = node.get('assignee')
    context = {}
    if source:
        if source['source'] == 'department_leader':
            from apps.core.appointments import department_leader
            leader, context = department_leader(application, source['levels'])
            users = users.filter(pk=leader.pk)
        if source['source'] == 'role':
            from apps.permissions.models import Role
            role = Role.objects.filter(pk=source['role_id'], is_active=True)
            if application.tenant_id:
                role = role.filter(tenant_id=application.tenant_id)
            if not role.exists():
                raise APIValidationError('动态审批角色不存在、已停用或不属于当前租户')
            users = users.filter(roles__role_id=source['role_id'], roles__role__is_active=True)
        elif source['source'] == 'applicant':
            users = users.filter(pk=application.applicant_id)
        found = list(users.distinct().order_by('pk')[:101])
    else:
        identifiers = node['assignee_ids']
        mapping = {str(row.pk): row for row in users.filter(pk__in=identifiers)}
        found = [mapping[str(UUID(key))] for key in identifiers if str(UUID(key)) in mapping]
        if len(found) != len(identifiers):
            found = []
    if not 1 <= len(found) <= 100:
        raise APIValidationError('当前节点没有有效审批人或人数超过100，请管理员检查角色和租户成员')
    return found, context


def resolve_assignees(application, node):
    return resolve_assignment(application, node)[0]
