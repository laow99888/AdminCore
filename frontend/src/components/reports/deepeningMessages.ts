import { registerUiMessages } from '@/i18n/uiText'
registerUiMessages({
  '时间比较': 'Period comparison', '不比较': 'No comparison', '环比（上期等长）': 'Previous period (same duration)',
  '同比（上年同日）': 'Previous year (same dates)', '比较日期字段': 'Comparison date field',
  '开始日期（含）': 'Start date (inclusive)', '结束日期（不含）': 'End date (exclusive)',
  '比较按本地时区的日期区间统计，最多366天；使用非日期分类维度。变化率基期为0时留空。': 'Compare local calendar dates, up to 366 days, grouped by non-date categories. Percentage change is blank when the baseline is zero.',
  '请填写有效比较区间，移除日期维度、饼图和同日期字段的固定筛选。': 'Enter a valid comparison interval and remove date dimensions, pie charts, and fixed filters on the comparison date field.',
  '带点号的指标来自登记的明细数值字段，与主表分别汇总，避免重复累计主表金额。': 'Dotted metrics are registered numeric detail fields. They are aggregated separately from parent records to avoid double counting parent amounts.',
  '明细按当前权限重新查询；时间比较仅下钻本期。每行对应一条主记录，明细指标显示该记录的汇总。': 'Details are queried with current permissions, for the current period only. Each row is one parent record, with its detail metrics aggregated.',
  '本期 {p0} 至 {p1}（结束日期不含当日）': 'Current period: {p0} to {p1} (exclusive end)',
})
