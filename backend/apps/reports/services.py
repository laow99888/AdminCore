"""Single-source aggregation and authorized, bounded drill-down share the same query."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db.models import DateField, F
from django.db.models.functions import TruncDate, TruncMonth, TruncQuarter, TruncWeek, TruncYear
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.query_budget import query_budget
from apps.core.data_scope import scope_queryset
from apps.files.access import file_queryset_for_actor
from apps.files.models import FileModel
from apps.tasks.models import TaskRecord
from .sources import source_specs, permitted_fields, field_types
from .validators import validate_definition
from .aggregation import aggregate_period, annotate_detail_rows
from .comparison import compare_rows, period_queryset


def catalog_for(user):
    result = []
    for key, spec in source_specs().items():
        fields = permitted_fields(user, key, spec)
        if not fields:
            continue
        result.append({'key': key, 'label': spec['label'],
                       **{kind: sorted(spec[kind] & fields) for kind in ('dimensions', 'metrics', 'filters')},
                       'field_types': {name: kind for name, kind in field_types(key, spec).items() if name in fields}})
    return result


def metrics_for(definition):
    return definition.get('metrics', [{'key': 'value', 'label': 'value', **definition.get('metric', {})}])


def authorize_definition(user, definition):
    spec = source_specs()[definition['data_source']]
    allowed = permitted_fields(user, definition['data_source'], spec)
    configured = ({x['field'] for x in definition['dimensions']} | {x['field'] for x in metrics_for(definition)}
                  | {x['field'] for x in definition['filters']})
    if 'comparison' in definition:
        configured.add(definition['comparison']['field'])
    if not configured <= allowed:
        raise PermissionError('当前字段权限不足，无法运行该报表')
    return spec, allowed


def filtered_queryset(user, definition):
    spec, _ = authorize_definition(user, definition)
    if 'service' in spec:
        queryset = spec['service'].visible(user)
    elif definition['data_source'] == 'users':
        queryset = scope_queryset(get_user_model().objects.all(), user, 'user', 'pk')
    elif definition['data_source'] == 'tasks':
        queryset = scope_queryset(TaskRecord.objects.all(), user, 'task', 'creator_id')
    else:
        queryset = file_queryset_for_actor(FileModel.objects.filter(is_deleted=False), user)
    for item in definition['filters']:
        field, op, value = item['field'], item['operator'], item['value']
        lookup = {'eq': field, 'in': f'{field}__in', 'gte': f'{field}__gte', 'lte': f'{field}__lte', 'contains': f'{field}__icontains'}[op]
        queryset = queryset.filter(**{lookup: value})
    return queryset.order_by()


def grouped_queryset(queryset, dimensions, *, prefix='', parent_model=None):
    values = []
    functions = {'week': TruncWeek, 'month': TruncMonth, 'quarter': TruncQuarter, 'year': TruncYear}
    for item in dimensions:
        field = prefix + item['field']
        kind = (parent_model or queryset.model)._meta.get_field(item['field']).get_internal_type()
        if kind in {'DateField', 'DateTimeField'}:
            alias = f'report_group_date_{len(values)}'
            grain = item.get('grain', 'day')
            # A DateField output applies the timezone once; nesting TruncDate over
            # TruncMonth would shift PostgreSQL midnight buckets a second time.
            expression = functions[grain](field, output_field=DateField()) if grain in functions else TruncDate(field)
            if kind == 'DateField' and grain == 'day':
                values.append(field)
                continue
            queryset = queryset.annotate(**{alias: expression})
            values.append(alias)
        else:
            if prefix:
                alias = f'report_parent_dimension_{len(values)}'
                queryset = queryset.annotate(**{alias: F(field)})
                values.append(alias)
            else:
                values.append(field)
    return queryset, values


def serialize_rows(rows):
    return [{key: format(value, 'f') if isinstance(value, Decimal) else value for key, value in row.items()} for row in rows]


def execute_definition(user, definition):
    definition = validate_definition(definition)
    return execute_prepared(user, definition)


def execute_prepared(user, definition):
    queryset = filtered_queryset(user, definition)
    spec, _ = authorize_definition(user, definition)
    dimensions = [item['field'] for item in definition['dimensions']]
    metrics = metrics_for(definition)
    with query_budget():
        if 'comparison' in definition:
            comparison = definition['comparison']
            current = aggregate_period(period_queryset(queryset, comparison), definition, spec, metrics, grouped_queryset)
            previous = aggregate_period(period_queryset(queryset, comparison, previous=True), definition, spec, metrics, grouped_queryset)
            rows, truncated = compare_rows(current, previous, dimensions, metrics, definition['limit'])
        else:
            rows = aggregate_period(queryset, definition, spec, metrics, grouped_queryset)
            truncated = len(rows) > definition['limit']
    columns = [item['key'] + suffix for item in metrics for suffix in
               (('', '_previous', '_delta', '_rate') if 'comparison' in definition else ('',))]
    labels = {item['key']: item['label'] for item in metrics}
    if 'comparison' in definition:
        for item in metrics:
            labels.update({item['key'] + suffix: item['label'] + label for suffix, label in
                           [('_previous', '·基期'), ('_delta', '·差额'), ('_rate', '·变化率(%)')]})
    return {'columns': dimensions + columns, 'rows': serialize_rows(rows[:definition['limit']]),
            'truncated': truncated, 'column_labels': labels,
            'chart_columns': [item['key'] + suffix for item in metrics for suffix in
                              (('', '_previous') if 'comparison' in definition else ('',))],
            'generated_at': timezone.now().isoformat(), 'definition': definition}


def drill_down(user, definition, group, page=1, page_size=20, *, prepared=False):
    if not prepared:
        definition = validate_definition(definition)
    if type(page) is not int or not 1 <= page <= 100 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValidationError('明细页码为1至100，每页为1至100条')
    fields = [item['field'] for item in definition['dimensions']]
    if not isinstance(group, dict) or set(group) != set(fields):
        raise ValidationError('明细必须提供完整的已登记维度')
    queryset = filtered_queryset(user, definition)
    if 'comparison' in definition:
        queryset = period_queryset(queryset, definition['comparison'])
    queryset, aliases = grouped_queryset(queryset, definition['dimensions'])
    for field, alias in zip(fields, aliases):
        value = group[field]
        if isinstance(value, (list, dict)):
            raise ValidationError('明细维度值必须为标量')
        try:
            value = DateField().to_python(value) if alias != field else queryset.model._meta.get_field(field).to_python(value)
        except (ValueError, TypeError, OverflowError, ModelValidationError):
            raise ValidationError('明细维度值无效') from None
        queryset = queryset.filter(**{alias: value})
    # Only projected aggregate fields, never arbitrary serializer/model fields.
    spec, allowed = authorize_definition(user, definition)
    metrics = metrics_for(definition)
    columns = list(dict.fromkeys(['id', *fields, *(item['field'] for item in metrics
                                                if item['field'] not in spec.get('detail_metrics', {}))]))
    columns = [field for field in columns if field in allowed]
    detail_metrics = [item for item in metrics if item['field'] in spec.get('detail_metrics', {})]
    queryset = annotate_detail_rows(queryset, detail_metrics, spec)
    columns += [item['key'] for item in detail_metrics]
    with query_budget():
        rows = list(queryset.order_by('pk').values(*columns)[(page - 1) * page_size:page * page_size + 1])
    return {'columns': columns, 'rows': serialize_rows(rows[:page_size]), 'page': page,
            'page_size': page_size, 'has_more': len(rows) > page_size,
            'column_labels': {item['key']: item['label'] + '·本单明细汇总' for item in detail_metrics}}
