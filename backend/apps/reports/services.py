from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from apps.core.query_budget import query_budget
from apps.core.data_scope import scope_queryset
from apps.files.access import file_queryset_for_actor
from apps.permissions.field_permissions import allowed_fields
from apps.files.models import FileModel
from apps.tasks.models import TaskRecord
from .validators import DATA_SOURCES

User = get_user_model()


def catalog_for(user):
    result = []
    for key, spec in DATA_SOURCES.items():
        fields = allowed_fields(user, spec['resource'], 'read')
        result.append({'key': key, 'label': spec['label'], 'dimensions': sorted(spec['dimensions'] & fields), 'metrics': sorted(spec['metrics'] & fields), 'filters': sorted(spec['filters'] & fields)})
    return result


def execute_definition(user, definition):
    spec = DATA_SOURCES[definition['data_source']]
    allowed = allowed_fields(user, spec['resource'], 'read')
    configured = {x['field'] for x in definition['dimensions']} | {definition['metric']['field']} | {x['field'] for x in definition['filters']}
    if not configured <= allowed:
        raise PermissionError('当前字段权限不足，无法运行该报表')
    if definition['data_source'] == 'users':
        queryset = scope_queryset(User.objects.all(), user, 'user', 'pk')
    elif definition['data_source'] == 'tasks':
        queryset = scope_queryset(TaskRecord.objects.all(), user, 'task', 'creator_id')
    else:
        queryset = file_queryset_for_actor(FileModel.objects.filter(is_deleted=False), user)
    for item in definition['filters']:
        field, op, value = item['field'], item['operator'], item['value']
        lookup = {'eq': field, 'in': f'{field}__in', 'gte': f'{field}__gte', 'lte': f'{field}__lte', 'contains': f'{field}__icontains'}[op]
        queryset = queryset.filter(**{lookup: value})
    dimensions = [item['field'] for item in definition['dimensions']]
    values = []
    annotations = {}
    for field in dimensions:
        if field == 'created_at' or field == 'date_joined':
            alias = f'group_date_{len(values)}'
            queryset = queryset.annotate(**{alias: TruncDate(field)})
            values.append(alias)
        else:
            values.append(field)
    metric = definition['metric']
    aggregation = {'count': Count, 'sum': Sum, 'avg': Avg}[metric['aggregation']]
    annotations['value'] = aggregation(metric['field'])
    with query_budget():
        if values:
            grouped = queryset.values(*values).annotate(**annotations).order_by(*values)[:definition['limit']]
            rows = [{**{field: row[alias] for field, alias in zip(dimensions, values)}, 'value': row['value']}
                    for row in grouped]
        else:
            rows = [queryset.aggregate(**annotations)]
    columns = [item['field'] for item in definition['dimensions']] + ['value']
    return {'columns': columns, 'rows': rows, 'generated_at': timezone.now().isoformat(), 'definition': definition}
