import re
from django.db.models import DateTimeField
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

CODE_RE = re.compile(r'^[a-z][a-z0-9-]{1,63}$')
CHART_TYPES = {'table', 'bar', 'line', 'pie', 'area'}
AGGREGATIONS = {'count', 'sum', 'avg'}
OPERATORS = {'eq', 'in', 'gte', 'lte', 'contains'}

DATA_SOURCES = {
    'users': {
        'label': '用户', 'resource': 'user', 'model': 'auth.User',
        'dimensions': {'username', 'is_active', 'date_joined'},
        'metrics': {'id', 'login_count'}, 'filters': {'username', 'is_active', 'date_joined'},
    },
    'tasks': {
        'label': '任务', 'resource': 'tasks', 'model': 'apps.tasks.models.TaskRecord',
        'dimensions': {'status', 'task_type', 'created_at'},
        'metrics': {'id', 'progress'}, 'filters': {'status', 'task_type', 'created_at'},
    },
    'files': {
        'label': '文件', 'resource': 'files', 'model': 'apps.files.models.FileModel',
        'dimensions': {'file_type', 'purpose', 'created_at'},
        'metrics': {'id', 'size', 'download_count'}, 'filters': {'file_type', 'purpose', 'created_at'},
    },
}


def validate_definition(value):
    if not isinstance(value, dict) or set(value) - {'data_source', 'chart_type', 'dimensions', 'metric', 'filters', 'limit'}:
        raise ValidationError('报表定义包含未登记属性')
    source = value.get('data_source')
    spec = DATA_SOURCES.get(source) if isinstance(source, str) else None
    if not spec:
        raise ValidationError('数据源不在白名单内')
    chart = value.get('chart_type', 'table')
    if not isinstance(chart, str) or chart not in CHART_TYPES:
        raise ValidationError('图表类型不受支持')
    dimensions = value.get('dimensions', [])
    if not isinstance(dimensions, list) or len(dimensions) > 2 or any(not isinstance(x, dict) or set(x) != {'field'} for x in dimensions):
        raise ValidationError('维度最多两个，且必须只包含 field')
    dim_fields = [x['field'] for x in dimensions]
    if any(not isinstance(field, str) for field in dim_fields):
        raise ValidationError('维度字段必须为文本')
    if len(set(dim_fields)) != len(dim_fields) or not set(dim_fields) <= spec['dimensions']:
        raise ValidationError('维度字段不在数据源白名单内')
    metric = value.get('metric', {'field': 'id', 'aggregation': 'count'})
    if (not isinstance(metric, dict) or set(metric) != {'field', 'aggregation'}
            or not isinstance(metric['field'], str) or not isinstance(metric['aggregation'], str)
            or metric['field'] not in spec['metrics'] or metric['aggregation'] not in AGGREGATIONS):
        raise ValidationError('指标字段或聚合方式无效')
    if metric['aggregation'] == 'count' and metric['field'] != 'id':
        raise ValidationError('count 只能统计 id')
    if metric['aggregation'] in {'sum', 'avg'} and metric['field'] == 'id':
        raise ValidationError('sum/avg 不能统计 id')
    filters = value.get('filters', [])
    if not isinstance(filters, list) or len(filters) > 3:
        raise ValidationError('筛选条件最多三个')
    normalized_filters = []
    for item in filters:
        if (not isinstance(item, dict) or set(item) != {'field', 'operator', 'value'}
                or not isinstance(item['field'], str) or not isinstance(item['operator'], str)
                or item['field'] not in spec['filters'] or item['operator'] not in OPERATORS):
            raise ValidationError('筛选条件不在白名单内')
        val = item['value']
        if item['operator'] == 'in' and (not isinstance(val, list) or len(val) > 50):
            raise ValidationError('in 筛选值必须为最多50项数组')
        if item['operator'] != 'in' and isinstance(val, (dict, list)):
            raise ValidationError('筛选值必须为标量')
        field = item['field']
        for scalar in val if item['operator'] == 'in' else [val]:
            if field == 'is_active':
                if type(scalar) is not bool or item['operator'] not in {'eq', 'in'}:
                    raise ValidationError('布尔筛选仅支持 eq/in 和布尔值')
            elif field in {'created_at', 'date_joined'}:
                if not isinstance(scalar, str) or item['operator'] == 'contains':
                    raise ValidationError('日期筛选值或操作符无效')
                try:
                    DateTimeField().to_python(scalar)
                except (DjangoValidationError, ValueError, OverflowError):
                    raise ValidationError('日期筛选必须使用有效的 ISO 日期或时间') from None
            elif not isinstance(scalar, str) or len(scalar) > 200:
                raise ValidationError('文本筛选值必须为最多200字符的文本')
        normalized_filters.append({'field': item['field'], 'operator': item['operator'], 'value': val})
    limit = value.get('limit', 100)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError('结果数量必须为1至100')
    return {'data_source': source, 'chart_type': chart, 'dimensions': [{'field': f} for f in dim_fields], 'metric': metric, 'filters': normalized_filters, 'limit': limit}
