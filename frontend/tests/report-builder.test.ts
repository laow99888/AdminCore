import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAuthStore } from '../src/stores/auth'
import { reportsApi, type ReportDefinition } from '../src/api'
import ReportBuilderView from '../src/views/reports/ReportBuilderView.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api', () => ({ reportsApi: {
  catalog: vi.fn(), list: vi.fn(), publish: vi.fn(), run: vi.fn(), update: vi.fn(),
} }))
vi.mock('../src/components', () => ({ AppLayout: defineComponent({ template: '<main><slot /></main>' }) }))
vi.mock('../src/components/common/BaseChart.vue', () => ({ default: defineComponent({ template: '<div />' }) }))

const definition: ReportDefinition = {
  id: 'report-fixture', name: '任务报表', code: 'tasks', kind: 'report', status: 'draft', version: 1,
  definition: { data_source: 'tasks', chart_type: 'table', dimensions: [{ field: 'status' }],
    metric: { field: 'id', aggregation: 'count' }, filters: [], limit: 100 },
  created_at: '', updated_at: '',
}
const catalog = [{ key: 'tasks', label: '任务', dimensions: ['status'], metrics: ['id'], filters: ['status'] }]

async function mountReport() {
  const pinia = createPinia(), auth = useAuthStore(pinia)
  auth.token = 'isolated-report-test'
  auth.user = { id: 'fixture', username: 'fixture', email: '', avatar: '', is_staff: true, permissions: ['*'] }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/report', component: { template: '<div />' } }] })
  await router.push('/report')
  return mount(ReportBuilderView, { global: { plugins: [pinia, router, ElementPlus] } })
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(reportsApi.catalog).mockResolvedValue(catalog)
  vi.mocked(reportsApi.list).mockResolvedValue({ items: [definition],
    pagination: { page: 1, page_size: 100, total: 1, total_pages: 1 } })
  vi.mocked(reportsApi.publish).mockResolvedValue({ data: { data: { ...definition, status: 'published' } } } as Awaited<ReturnType<typeof reportsApi.publish>>)
  vi.mocked(reportsApi.update).mockResolvedValue({ data: { data: definition } } as Awaited<ReturnType<typeof reportsApi.update>>)
  vi.mocked(reportsApi.run).mockResolvedValue({ columns: ['value'], rows: [{ value: 3 }],
    definition: { chart_type: 'table' }, generated_at: '' })
})

it.each([false, true])('保存后的目录重载期间禁用发布，重载失败=%s后可发布', async failed => {
  let finish!: (value: typeof catalog) => void
  let reject!: (error: Error) => void
  const pending = new Promise<typeof catalog>((resolve, fail) => { finish = resolve; reject = fail })
  const wrapper = await mountReport()
  await flushPromises()
  await wrapper.get('tbody tr').trigger('click')
  vi.mocked(reportsApi.catalog).mockReturnValueOnce(pending)
  const button = (text: string) => wrapper.findAll<HTMLButtonElement>('button').find(item => item.text() === text)!
  await button('保存草稿').trigger('click')
  await flushPromises()
  expect(reportsApi.update).toHaveBeenCalledOnce()
  expect(button('发布').element.disabled).toBe(true)
  expect(reportsApi.publish).not.toHaveBeenCalled()
  if (failed) reject(new Error('目录重载失败'))
  else finish(catalog)
  await flushPromises()
  expect(button('发布').element.disabled).toBe(false)
  await button('发布').trigger('click')
  await flushPromises()
  expect(reportsApi.publish).toHaveBeenCalledExactlyOnceWith('report-fixture', 1)
  wrapper.unmount()
})

it.each([false, true])('发布后的目录重载期间禁用运行，重载失败=%s后恢复操作', async failed => {
  let finish!: (value: typeof catalog) => void
  let reject!: (error: Error) => void
  const pending = new Promise<typeof catalog>((resolve, fail) => { finish = resolve; reject = fail })
  const wrapper = await mountReport()
  await flushPromises()
  await wrapper.get('tbody tr').trigger('click')
  vi.mocked(reportsApi.catalog).mockReturnValueOnce(pending)
  const button = (text: string) => wrapper.findAll<HTMLButtonElement>('button').find(item => item.text() === text)!
  await button('发布').trigger('click')
  await flushPromises()
  expect(reportsApi.publish).toHaveBeenCalledWith('report-fixture', 1)
  expect(button('运行').element.disabled).toBe(true)
  expect(reportsApi.run).not.toHaveBeenCalled()
  if (failed) reject(new Error('目录重载失败'))
  else finish(catalog)
  await flushPromises()
  expect(button('运行').element.disabled).toBe(false)
  if (failed) expect(wrapper.text()).toContain('目录重载失败')
  await button('运行').trigger('click')
  await flushPromises()
  expect(reportsApi.run).toHaveBeenCalledExactlyOnceWith('report-fixture')
  wrapper.unmount()
})
