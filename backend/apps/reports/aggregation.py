"""Aggregate parent and each registered child separately, never a fan-out join."""
from django.db.models import Avg, Count, F, Q, Subquery, Sum


AGGREGATES = {'count': Count, 'sum': Sum, 'avg': Avg}


def child_queryset(detail, parents):
    return detail['model'].objects.filter(parent_id__in=Subquery(parents.values('pk'))).filter(
        Q(tenant_id=F('parent__tenant_id')) | Q(tenant_id__isnull=True, parent__tenant_id__isnull=True))


def aggregate_period(queryset, definition, spec, metrics, group_queryset):
    dimensions = definition['dimensions']
    fields = [item['field'] for item in dimensions]
    grouped, aliases = group_queryset(queryset, dimensions)
    roots = [item for item in metrics if item['field'] not in spec.get('detail_metrics', {})]
    annotations = {item['key']: AGGREGATES[item['aggregation']](item['field']) for item in roots}
    # Even child-only reports derive their bounded group domain from visible parents.
    annotations['_report_rows'] = Count('pk')
    if aliases:
        records = list(grouped.values(*aliases).annotate(**annotations).order_by(
            *(F(alias).asc(nulls_first=True) for alias in aliases))[:definition['limit'] + 1])
    else:
        records = [queryset.aggregate(**annotations)]
    rows = [{**{field: row[alias] for field, alias in zip(fields, aliases)},
             **{item['key']: row[item['key']] for item in roots}} for row in records]
    if aliases and not rows:
        return rows
    selected = Q()
    for row in records:
        selected |= Q(**{alias: row[alias] for alias in aliases})
    selected_parents = grouped.filter(selected) if aliases else queryset
    child_groups = {}
    for item in metrics:
        detail = spec.get('detail_metrics', {}).get(item['field'])
        if detail:
            child_groups.setdefault(detail['group'], []).append((item, detail))
    for items in child_groups.values():
        child = child_queryset(items[0][1], selected_parents)
        # Group through explicit parent fields only; the service has already scoped parent IDs.
        child, child_aliases = group_queryset(child, dimensions, prefix='parent__', parent_model=queryset.model)
        annotations = {item['key']: AGGREGATES[item['aggregation']](detail['field']) for item, detail in items}
        results = list(child.values(*child_aliases).annotate(**annotations).order_by()) if aliases else [child.aggregate(**annotations)]
        indexed = {tuple(record[alias] for alias in child_aliases): record for record in results}
        for row in rows:
            values = indexed.get(tuple(row[field] for field in fields), {})
            row.update({item['key']: values.get(item['key']) for item, _ in items})
    return rows


def annotate_detail_rows(queryset, metrics, spec):
    """Drill down stays one row per parent; detail metrics are per-parent aggregates."""
    from django.db.models import OuterRef
    for metric in metrics:
        detail = spec.get('detail_metrics', {}).get(metric['field'])
        if detail:
            children = detail['model'].objects.filter(parent_id=OuterRef('pk')).filter(
                Q(tenant_id=OuterRef('tenant_id')) | Q(tenant_id__isnull=True, parent__tenant_id__isnull=True))
            value = children.order_by().values('parent_id').annotate(
                _value=AGGREGATES[metric['aggregation']](detail['field'])).values('_value')
            queryset = queryset.annotate(**{metric['key']: Subquery(value)})
    return queryset
