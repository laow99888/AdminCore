import { expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import BaseChart from '../src/components/common/BaseChart.vue'
import type { ReportCatalogItem } from '../src/api'
import { newReportQuery, type ReportResult } from '../src/api/reportTypes'
import ReportQueryEditor from '../src/components/reports/ReportQueryEditor.vue'
import ReportResultTable from '../src/components/reports/ReportResultTable.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string, params: Record<string,unknown> = {}) => text.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? '')), registerUiMessages: vi.fn() }))
vi.mock('../src/components/common/BaseChart.vue', () => ({ default: defineComponent({ props: ['option','table'], template: '<div class="chart" />' }) }))
const catalog: ReportCatalogItem[] = [{ key: 'orders', label: '采购', dimensions: ['status','created_at'], metrics: ['id','amount','lines.quantity'], filters: ['status','created_at'], field_types: { created_at: 'datetime', status: 'text' } }]

it('保存同环比区间、明细指标与切换数据源后的清理', async () => {
  const model = ref(newReportQuery('orders'))
  const Host = defineComponent({ components: { ReportQueryEditor }, setup: () => ({ model,catalog }), template: '<ReportQueryEditor v-model="model" :catalog="catalog" />' })
  const wrapper = mount(Host), editor = wrapper.getComponent(ReportQueryEditor)
  await wrapper.get('[aria-label="时间比较"]').setValue('previous_period')
  expect(editor.emitted('valid')!.at(-1)).toEqual([false])
  await wrapper.get('[aria-label="开始日期（含）"]').setValue('2026-03-01')
  await wrapper.get('[aria-label="结束日期（不含）"]').setValue('2026-04-01')
  expect(editor.emitted('valid')!.at(-1)).toEqual([true])
  await wrapper.get('[aria-label="时间比较"]').setValue('previous_year')
  expect(model.value.comparison).toEqual({ field: 'created_at', mode: 'previous_year', start: '2026-03-01', end: '2026-04-01' })
  await wrapper.get('[aria-label="指标字段"]').setValue('lines.quantity')
  expect(model.value.metrics![0]).toMatchObject({ field: 'lines.quantity', aggregation: 'sum' })
  expect(wrapper.text()).toContain('避免重复累计主表金额')
  await wrapper.get('[aria-label="数据源"]').trigger('change')
  expect(model.value.comparison).toBeUndefined()
  expect(model.value.metrics![0].field).toBe('id')
  wrapper.unmount()
})

it.each(['invalid-date','range','date-dimension','pie','fixed-date'])('阻止无效比较配置 %s', async kind => {
  const model = ref({ ...newReportQuery('orders'), comparison: { field: 'created_at', mode: 'previous_period' as const, start: '2026-03-01', end: '2026-04-01' } })
  const Host = defineComponent({ components: { ReportQueryEditor }, setup: () => ({ model,catalog }), template: '<ReportQueryEditor v-model="model" :catalog="catalog" />' })
  const wrapper = mount(Host)
  if (kind === 'invalid-date') model.value.comparison.start = '2026-02-30'
  else if (kind === 'range') model.value.comparison.end = '2027-04-01'
  else if (kind === 'date-dimension') model.value.dimensions = [{ field: 'created_at' }]
  else if (kind === 'pie') model.value.chart_type = 'pie'
  else model.value.filters = [{ field: 'created_at', operator: 'gte', value: '2026-01-01' }]
  await nextTick()
  expect(wrapper.getComponent(ReportQueryEditor).emitted('valid')!.at(-1)).toEqual([false])
  expect(wrapper.get('[role="alert"]').text()).toContain('有效比较区间')
  wrapper.unmount()
})

it('图表只绘制本期和基期，表格保留差额与空变化率', () => {
  const definition = { ...newReportQuery('orders'), chart_type: 'bar' as const, comparison: { field: 'created_at', mode: 'previous_period' as const, start: '2026-03-01', end: '2026-04-01' } }
  const result: ReportResult = { definition, generated_at: '', columns: ['m_count','m_count_previous','m_count_delta','m_count_rate'], chart_columns: ['m_count','m_count_previous'], column_labels: { m_count: '本期', m_count_previous: '基期', m_count_delta: '差额', m_count_rate: '变化率' }, rows: [{ m_count: 3, m_count_previous: 0, m_count_delta: '3', m_count_rate: null }] }
  const wrapper = mount(ReportResultTable,{ props: { result, caption: '比较', busy: false } })
  const option = wrapper.getComponent(BaseChart).props('option') as { series: Array<{ name: string; data: number[] }> }
  expect(option.series.map(item => item.name)).toEqual(['本期','基期'])
  expect(wrapper.findAll('thead th').map(item => item.text())).toContain('变化率')
  expect(wrapper.text()).toContain('2026-03-01')
  expect(wrapper.findAll('tbody td')[3].text()).toBe('')
  wrapper.unmount()
})
