import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { useAuthStore } from '../src/stores/auth'
import { useTenantStore } from '../src/stores/tenants'
import { reportsApi, type ReportDefinition } from '../src/api'
import { displayReportCell, newReportQuery, type DashboardDesign, type DashboardResult, type ReportOutput } from '../src/api/reportTypes'
import ReportViewer from '../src/components/reports/ReportViewer.vue'
import ReportBuilderView from '../src/views/reports/ReportBuilderView.vue'
import ReportQueryEditor from '../src/components/reports/ReportQueryEditor.vue'
import ReportValueInput from '../src/components/reports/ReportValueInput.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value.replace('{p0}','1'), registerUiMessages: vi.fn() }))
vi.mock('../src/api', () => ({ reportsApi: { catalog: vi.fn(), list: vi.fn(), publish: vi.fn(), run: vi.fn(), update: vi.fn(), create: vi.fn(), details: vi.fn() } }))
vi.mock('../src/components', () => ({ AppLayout: defineComponent({ template: '<main><slot /></main>' }) }))
vi.mock('../src/components/common/BaseChart.vue', () => ({ default: defineComponent({ template: '<div />' }) }))
vi.mock('../src/components/common/BaseDialog.vue', () => ({ default: defineComponent({ props: ['modelValue'], template: '<aside v-if="modelValue"><slot /><slot name="footer" /></aside>' }) }))

const catalog = [{ key: 'tasks', label: '任务', dimensions: ['status','created_at'], metrics: ['id','progress'], filters: ['status','task_type'], field_types: { status: 'text' as const, created_at: 'datetime' as const } }]
function design(): DashboardDesign {
  return { schema_version: 2, widgets: [{ key: 'distribution', title: '状态分布', span: 6, definition: { ...newReportQuery(), dimensions: [{ field: 'status' }] } },
    { key: 'total', title: '合计', span: 6, definition: newReportQuery() }],
  filters: [{ key: 'kind', label: '业务类型', operator: 'eq', value: 'purchase', bindings: [{ widget: 'distribution', field: 'task_type' },{ widget: 'total', field: 'task_type' }] }],
  links: [{ source: 'distribution', source_field: 'status', target: 'total', target_field: 'status' }] }
}
function output(): DashboardResult {
  const definition = design()
  return { schema_version: 2, definition, generated_at: '', widgets: definition.widgets.map(widget => ({ ...widget, result: { definition: widget.definition, generated_at: '', columns: widget.key === 'distribution' ? ['status','m_count'] : ['m_count'], rows: widget.key === 'distribution' ? [{ status: 'success', m_count: 3 }] : [{ m_count: 5 }] } })) }
}
const report: ReportDefinition = { id: 'fixture', name: '采购看板', code: 'board', kind: 'dashboard', status: 'published', version: 1, definition: design(), created_at: '', updated_at: '' }
function setup() { const pinia = createPinia(), auth = useAuthStore(pinia); auth.token = 'test-token'; auth.user = { id: 'admin', username: 'admin', email: '', avatar: '', is_staff: true, permissions: ['*'] }; return { pinia,auth } }
function button(wrapper: ReturnType<typeof mount>, label: string) { return wrapper.findAll<HTMLButtonElement>('button').find(item => item.text() === label)! }
function field(wrapper: ReturnType<typeof mount>, label: string) { return wrapper.findAll('label').find(item => item.find('span').text() === label)!.get('input,select') }
beforeEach(() => { vi.resetAllMocks(); vi.mocked(reportsApi.catalog).mockResolvedValue(catalog); vi.mocked(reportsApi.list).mockResolvedValue({ items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 } }); vi.mocked(reportsApi.run).mockResolvedValue(output()); vi.mocked(reportsApi.details).mockResolvedValue({ columns: ['id'], rows: [{ id: 'mine' }], page: 1, page_size: 20, has_more: true }) })

it('运行统一筛选、表格联动和明细分页使用同一组条件', async () => {
  const { pinia } = setup()
  const wrapper = mount(ReportViewer,{ props: { report, initial: output(), catalog }, global: { plugins: [pinia,ElementPlus] } })
  await flushPromises()
  await field(wrapper,'业务类型').setValue('invoice')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(reportsApi.run).toHaveBeenLastCalledWith('fixture',{ filters: { kind: 'invoice' } },expect.any(AbortSignal))
  await button(wrapper,'联动筛选').trigger('click'); await flushPromises()
  expect(reportsApi.run).toHaveBeenLastCalledWith('fixture',{ filters: { kind: 'invoice' },selection: { widget: 'distribution', field: 'status', value: 'success' } },expect.any(AbortSignal))
  await button(wrapper,'查看明细').trigger('click'); await flushPromises()
  expect(reportsApi.details).toHaveBeenLastCalledWith('fixture',expect.objectContaining({ widget: 'distribution', group: { status: 'success' },page: 1, options: { filters: { kind: 'invoice' }, selection: { widget: 'distribution', field: 'status', value: 'success' } } }),expect.any(AbortSignal))
  await button(wrapper,'下一页').trigger('click'); await flushPromises()
  expect(reportsApi.details).toHaveBeenLastCalledWith('fixture',expect.objectContaining({ page: 2 }),expect.any(AbortSignal))
  wrapper.unmount()
})

it.each(['identity','tenant','unmount'])('丢弃跨 %s 的运行响应并撤销请求', async kind => {
  let resolve!: (value: ReportOutput) => void
  vi.mocked(reportsApi.run).mockReturnValue(new Promise(finish => { resolve = finish }))
  const { pinia,auth } = setup(), tenants = useTenantStore(pinia)
  const wrapper = mount(ReportViewer,{ props: { report, initial: output(), catalog }, global: { plugins: [pinia,ElementPlus] } })
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const signal = vi.mocked(reportsApi.run).mock.calls[0][2]!
  if (kind === 'identity') auth.user = { ...auth.user!,id: 'other' }
  else if (kind === 'tenant') tenants.currentId = 'other-tenant'
  else wrapper.unmount()
  await flushPromises(); expect(signal.aborted).toBe(true)
  const late = output(); late.widgets[0].title = '旧身份的私密数据'; resolve(late); await flushPromises()
  if (kind !== 'unmount') { expect(wrapper.text()).not.toContain('旧身份的私密数据'); expect(wrapper.find('table').exists()).toBe(false); wrapper.unmount() }
})

it('下钻失败时清空旧图表和明细，避免沿用已撤销权限的数据', async () => {
  const { pinia } = setup()
  vi.mocked(reportsApi.details).mockRejectedValue(new Error('字段权限已收紧'))
  const wrapper = mount(ReportViewer,{ props: { report, initial: output(), catalog }, global: { plugins: [pinia,ElementPlus] } })
  await button(wrapper,'查看明细').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('字段权限已收紧'); expect(wrapper.find('table').exists()).toBe(false)
  wrapper.unmount()
})

it('尚未应用的筛选输入不改变已显示图表的明细条件', async () => {
  const { pinia } = setup()
  const wrapper = mount(ReportViewer,{ props: { report, initial: output(), catalog }, global: { plugins: [pinia,ElementPlus] } })
  await field(wrapper,'业务类型').setValue('not-applied')
  await button(wrapper,'查看明细').trigger('click'); await flushPromises()
  expect(reportsApi.details).toHaveBeenLastCalledWith('fixture',expect.objectContaining({ options: { filters: { kind: 'purchase' } } }),expect.any(AbortSignal))
  wrapper.unmount()
})

it('无效 JSON 筛选值阻止运行，并保留用户输入', async () => {
  const { pinia } = setup(), initial = output(); initial.definition.filters[0].operator = 'in'; initial.definition.filters[0].value = ['purchase']
  const wrapper = mount(ReportViewer,{ props: { report, initial, catalog }, global: { plugins: [pinia,ElementPlus] } })
  await field(wrapper,'业务类型').setValue('invalid json')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(reportsApi.run).not.toHaveBeenCalled(); expect(wrapper.get('[role="alert"]').text()).toContain('JSON')
  wrapper.unmount()
})

it('编辑器支持两维度、多指标与固定筛选，源变更清除旧字段', async () => {
  const model = ref(newReportQuery())
  const Host = defineComponent({ components: { ReportQueryEditor }, setup: () => ({ model,catalog }), template: '<ReportQueryEditor v-model="model" :catalog="catalog" />' })
  const wrapper = mount(Host)
  await button(wrapper,'添加维度').trigger('click'); await button(wrapper,'添加维度').trigger('click')
  expect(model.value.dimensions).toEqual([{ field: 'status' },{ field: 'created_at',grain: 'day' }])
  await button(wrapper,'添加指标').trigger('click'); expect(model.value.metrics).toHaveLength(2)
  await button(wrapper,'添加筛选').trigger('click'); expect(model.value.filters).toHaveLength(1)
  await field(wrapper,'数据源').trigger('change'); expect(model.value.dimensions).toEqual([]); expect(model.value.metrics).toHaveLength(1)
  wrapper.unmount()
})

it('构建器创建多组件草稿时保存布局和多指标定义', async () => {
  const { pinia } = setup()
  const router = createRouter({ history: createMemoryHistory(),routes: [{ path: '/reports',component: { template: '<div />' } }] }); await router.push('/reports')
  vi.mocked(reportsApi.create).mockResolvedValue({ data: { data: { ...report,status: 'draft' } } } as Awaited<ReturnType<typeof reportsApi.create>>)
  const wrapper = mount(ReportBuilderView,{ global: { plugins: [pinia,router,ElementPlus] } }); await flushPromises()
  await field(wrapper,'名称').setValue('采购看板'); await field(wrapper,'编码').setValue('purchase-board'); await field(wrapper,'类型').setValue('dashboard')
  await button(wrapper,'添加组件').trigger('click'); await button(wrapper,'保存草稿').trigger('click'); await flushPromises()
  const saved = vi.mocked(reportsApi.create).mock.calls[0][0]
  expect(saved.kind).toBe('dashboard'); expect((saved.definition as DashboardDesign).widgets).toHaveLength(2)
  expect((saved.definition as DashboardDesign).widgets[0].definition.metrics).toHaveLength(1)
  wrapper.unmount()
})

it('只读用户的配置控件禁用，运行权限不授予定义写入能力', async () => {
  const { pinia,auth } = setup(); auth.user = { ...auth.user!,is_staff: false,permissions: ['report:read','report:execute'] }
  vi.mocked(reportsApi.list).mockResolvedValue({ items: [report], pagination: { page: 1,page_size: 20,total: 1,total_pages: 1 } })
  const router = createRouter({ history: createMemoryHistory(),routes: [{ path: '/reports',component: { template: '<div />' } }] }); await router.push('/reports')
  const wrapper = mount(ReportBuilderView,{ global: { plugins: [pinia,router,ElementPlus] } }); await flushPromises()
  expect((field(wrapper,'名称').element as HTMLInputElement).matches(':disabled')).toBe(true)
  expect(button(wrapper,'新建草稿').element.disabled).toBe(true)
  expect(button(wrapper,'保存草稿').element.disabled).toBe(true)
  expect(button(wrapper,'发布').element.disabled).toBe(true)
  await button(wrapper,'运行').trigger('click'); await flushPromises(); expect(reportsApi.run).toHaveBeenCalledWith('fixture')
  await button(wrapper,'保存草稿').trigger('click'); expect(reportsApi.create).not.toHaveBeenCalled(); expect(reportsApi.update).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('布尔筛选使用真实布尔值，十进制输入保持文本精度', async () => {
  const bool = mount(ReportValueInput,{ props: { modelValue: true,kind: 'boolean',label: '启用' } })
  await bool.get('select').setValue('false'); expect(bool.emitted('update:modelValue')?.[0]).toEqual([false]); bool.unmount()
  const decimal = mount(ReportValueInput,{ props: { modelValue: '',kind: 'decimal',label: '金额' } })
  await decimal.get('input').setValue('123456789.10'); expect(decimal.emitted('update:modelValue')?.[0]).toEqual(['123456789.10']); decimal.unmount()
})

it('金额显示去除多余尾零时不经过浮点数，也不改变业务编码和原始结果', () => {
  const result = output().widgets[0].result
  result.definition.metrics = [{ key: 'm_amount',label: '金额',field: 'amount',aggregation: 'sum' }]
  expect(displayReportCell(result,'m_amount','123456789123456789.120000000')).toBe('123456789123456789.12')
  expect(displayReportCell(result,'m_amount','0.123456789123456789')).toBe('0.123456789123456789')
  expect(displayReportCell(result,'m_amount','-1.000000000')).toBe('-1.00')
  expect(displayReportCell(result,'status','001.2000')).toBe('001.2000')
})

it('旧版同名维度保持原样，按返回指标列格式化重命名聚合值', () => {
  const result = output().widgets[0].result
  result.definition = { chart_type: 'table', dimensions: [{ field: 'value' }], metric: { field: 'amount', aggregation: 'sum' } }
  result.columns = ['value', 'm_value']
  result.chart_columns = ['m_value']
  expect(displayReportCell(result,'value','001.00')).toBe('001.00')
  expect(displayReportCell(result,'value','001.2000')).toBe('001.2000')
  expect(displayReportCell(result,'m_value','123456789123456789.120000000')).toBe('123456789123456789.12')
  expect(displayReportCell(result,'m_value','-1.000000000')).toBe('-1.00')
})

it('无返回指标列的旧版结果继续兼容固定value指标', () => {
  const result = output().widgets[0].result
  result.definition = { chart_type: 'table', metric: { field: 'amount', aggregation: 'sum' } }
  delete result.chart_columns
  expect(displayReportCell(result,'value','123456789123456789.120000000')).toBe('123456789123456789.12')
  expect(displayReportCell(result,'status','001.2000')).toBe('001.2000')
})
