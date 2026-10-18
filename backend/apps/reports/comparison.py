"""Bounded, explicit calendar windows; all endpoints use [start, end)."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal, localcontext

from django.utils import timezone
from rest_framework.exceptions import ValidationError


def validate_comparison(value, spec, types, dimensions, chart):
    if (not isinstance(value, dict) or set(value) != {'field', 'mode', 'start', 'end'}
            or not isinstance(value['field'], str) or value['field'] not in spec['filters']
            or types.get(value['field']) not in {'date', 'datetime'}
            or value['mode'] not in ('previous_period', 'previous_year')):
        raise ValidationError('时间比较须指定已登记日期字段、比较方式和起止日期')
    try:
        if any(not isinstance(value[key], str) or len(value[key]) != 10 for key in ('start', 'end')):
            raise ValueError
        start, end = (date.fromisoformat(value[key]) for key in ('start', 'end'))
        if start.isoformat() != value['start'] or end.isoformat() != value['end'] or not 1 <= (end - start).days <= 366:
            raise ValueError
        previous_window(start, end, value['mode'])
    except (ValueError, TypeError, OverflowError):
        raise ValidationError('比较日期必须为 YYYY-MM-DD，结束日期不含当日，跨度为1至366天') from None
    if chart == 'pie' or any(types[item['field']] in {'date', 'datetime'} for item in dimensions):
        raise ValidationError('时间比较支持非日期分类维度和表格/柱线图，不能用于日期分桶或饼图')
    return dict(value)


def previous_window(start, end, mode):
    if mode == 'previous_period':
        return start - (end - start), start

    def last_year(value):
        return value.replace(year=value.year - 1, day=min(value.day, monthrange(value.year - 1, value.month)[1]))
    previous_start, previous_end = last_year(start), last_year(end)
    return previous_start, max(previous_end, previous_start + timedelta(days=1))


def period_queryset(queryset, comparison, *, previous=False):
    start, end = (date.fromisoformat(comparison[key]) for key in ('start', 'end'))
    if previous:
        start, end = previous_window(start, end, comparison['mode'])
    field = comparison['field']
    if queryset.model._meta.get_field(field).get_internal_type() == 'DateTimeField':
        zone = timezone.get_current_timezone()
        start, end = (timezone.make_aware(datetime.combine(value, time.min), zone) for value in (start, end))
    return queryset.filter(**{field + '__gte': start, field + '__lt': end})


def compare_rows(current, previous, dimensions, metrics, limit):
    def index(rows):
        return {tuple(row[field] for field in dimensions): row for row in rows}
    now, before = index(current), index(previous)
    keys = sorted(now.keys() | before.keys(), key=group_sort_key)
    rows = []
    for group in keys[:limit]:
        row = dict(zip(dimensions, group))
        for metric in metrics:
            key = metric['key']
            # A missing category has count=0, SUM/AVG=NULL, as in ordinary SQL aggregates.
            empty = 0 if metric['aggregation'] == 'count' else None
            value, baseline = now.get(group, {}).get(key, empty), before.get(group, {}).get(key, empty)
            row[key], row[key + '_previous'] = value, baseline
            if value is None or baseline is None:
                delta = rate = None
            else:
                with localcontext() as context:
                    context.prec = 64
                    delta = Decimal(str(value)) - Decimal(str(baseline))
                    rate = None if not baseline else delta / abs(Decimal(str(baseline))) * 100
                    if rate is not None:
                        rate = rate.quantize(Decimal('0.0001'))
            row[key + '_delta'], row[key + '_rate'] = delta, rate
        rows.append(row)
    return rows, len(keys) > limit


def group_sort_key(group):
    return tuple((value is not None, value) for value in group)
