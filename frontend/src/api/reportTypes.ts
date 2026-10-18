export type ReportFieldType = 'text' | 'integer' | 'decimal' | 'boolean' | 'date' | 'datetime'
export interface ReportMetric { key: string; label: string; field: string; aggregation: 'count' | 'sum' | 'avg' }
export interface ReportFilter { field: string; operator: 'eq' | 'in' | 'gte' | 'lte' | 'contains'; value: unknown }
export interface ReportQuery extends Record<string, unknown> {
  data_source: string
  chart_type: 'table' | 'bar' | 'line' | 'pie' | 'area'
  dimensions: Array<{ field: string; grain?: 'day' | 'week' | 'month' | 'quarter' | 'year' }>
  metric?: { field: string; aggregation: 'count' | 'sum' | 'avg' }
  metrics?: ReportMetric[]
  filters: ReportFilter[]
  limit: number
  comparison?: { field: string; mode: 'previous_period' | 'previous_year'; start: string; end: string }
}
export interface DashboardWidget { key: string; title: string; span: 6 | 12; definition: ReportQuery }
export interface DashboardFilter { key: string; label: string; operator: ReportFilter['operator']; value: unknown; bindings: Array<{ widget: string; field: string }> }
export interface DashboardLink { source: string; source_field: string; target: string; target_field: string }
export interface DashboardDesign extends Record<string, unknown> { schema_version: 2; widgets: DashboardWidget[]; filters: DashboardFilter[]; links: DashboardLink[] }
export interface ReportTable { columns: string[]; rows: Array<Record<string, unknown>>; column_labels?: Record<string, string>; chart_columns?: string[]; truncated?: boolean }
export interface ReportResult extends ReportTable { definition: Record<string, unknown>; generated_at: string }
export interface DashboardResult { schema_version: 2; widgets: Array<Pick<DashboardWidget, 'key' | 'title' | 'span'> & { result: ReportResult }>; definition: DashboardDesign; generated_at: string }
export type ReportOutput = ReportResult | DashboardResult
export interface ReportRunOptions { filters?: Record<string, unknown>; selection?: { widget: string; field: string; value: unknown } }
export interface ReportDetails extends ReportTable { page: number; page_size: number; has_more: boolean }

export function newReportQuery(source = 'tasks'): ReportQuery {
  return { data_source: source, chart_type: 'table', dimensions: [], metrics: [{ key: 'm_count', label: '记录数', field: 'id', aggregation: 'count' }], filters: [], limit: 100 }
}
export function asQuery(value: Record<string, unknown>): ReportQuery {
  const query = JSON.parse(JSON.stringify(value)) as ReportQuery
  if (!query.metrics) query.metrics = [{ key: 'm_value', label: '合计', ...(query.metric || { field: 'id', aggregation: 'count' }) }]
  delete query.metric
  return query
}
export function displayValue(value: unknown): string | number {
  return typeof value === 'number' || typeof value === 'string' ? value : value == null ? '' : String(value)
}
/** Trim redundant aggregate decimal zeroes without converting precise values to Number. */
export function displayReportCell(result: ReportResult, column: string, value: unknown): string | number {
  const metrics = result.definition.metrics as ReportMetric[] | undefined
  const metric = metrics ? metrics.some(item => item.key === column) : column === 'value'
  if (metric && typeof value === 'string' && /^-?\d+\.\d+$/.test(value)) {
    const [whole,fraction] = value.split('.')
    return `${whole}.${fraction.replace(/0+$/,'').padEnd(2,'0')}`
  }
  return displayValue(value)
}
