import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { useAuthStore } from '../src/stores/auth'
import { approvalFlowsApi, onlineFormsApi, reportsApi } from '../src/api'
import Flow from '../src/views/approvals/ApprovalFlowDesignerView.vue'
import Form from '../src/views/onlineForms/OnlineFormDesignerView.vue'
import Report from '../src/views/reports/ReportBuilderView.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/components/layout/AppLayout.vue', () => ({ default: defineComponent({ template: '<main><slot /></main>' }) }))
vi.mock('../src/components', () => ({
  AppLayout: defineComponent({ template: '<main><slot /></main>' }),
  BaseCard: defineComponent({ template: '<section><header><slot name="header" /></header><slot /></section>' }),
  BaseButton: defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }),
}))
vi.mock('../src/components/common/BaseChart.vue', () => ({ default: defineComponent({ template: '<div />' }) }))
vi.mock('../src/api', () => ({
  approvalFlowsApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), publish: vi.fn() },
  onlineFormsApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), publish: vi.fn() },
  reportsApi: { catalog: vi.fn(), list: vi.fn(), create: vi.fn(), update: vi.fn(), publish: vi.fn(), run: vi.fn() },
}))
const configs = [
  { name: '流程', component: Flow, api: approvalFlowsApi, definition: { nodes: [{ id: 'start', type: 'start' }, { id: 'review', type: 'user', assignee_ids: ['u'] }, { id: 'end', type: 'end' }], edges: [{ from: 'start', to: 'review' }, { from: 'review', to: 'end' }] } },
  { name: '表单', component: Form, api: onlineFormsApi, definition: { fields: [{ key: 'title', label: '标题', type: 'text' }] } },
  { name: '报表', component: Report, api: reportsApi, definition: { data_source: 'tasks', chart_type: 'table', dimensions: [], metric: { field: 'id', aggregation: 'count' }, filters: [], limit: 100 } },
]
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(reportsApi.catalog).mockResolvedValue([{ key: 'tasks', label: '任务', dimensions: ['status'], metrics: ['id'], filters: ['status'] }])
})
afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

for (const cfg of configs) {
  async function harness() {
    const row = { id: 'draft', name: '已保存名称', code: 'fixture', kind: 'report', status: 'draft', version: 7, definition: cfg.definition }
    vi.mocked(cfg.api.list).mockResolvedValue({ items: [row], pagination: { page: 1, page_size: 20, total: 101, total_pages: 6 } } as never)
    vi.mocked(cfg.api.update).mockImplementation(async (_id, value) => ({ data: { data: { ...row, ...value, version: 8 } } }) as never)
    vi.mocked(cfg.api.publish).mockResolvedValue({ data: { data: { ...row, name: '未保存名称', status: 'published', version: 8 } } } as never)
    const pinia = createPinia(), auth = useAuthStore(pinia)
    auth.token = 'isolated-editor'; auth.user = { id: 'editor', username: 'editor', email: '', avatar: '', permissions: ['*'], is_staff: true }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/edit', component: { template: '<div />' } }, { path: '/other', component: { template: '<div />' } }] })
    await router.push('/edit')
    const wrapper = mount(cfg.component, { global: { plugins: [pinia, router, ElementPlus] } })
    await flushPromises(); await wrapper.get('tbody tr').trigger('click'); await flushPromises()
    const button = (text: string) => wrapper.findAll('button').find(item => item.text() === text)!
    return { wrapper, button, router }
  }
  it(`${cfg.name}：发布先保存当前修改和版本，再发布新版本`, async () => {
    const { wrapper, button } = await harness()
    await wrapper.get('input').setValue('未保存名称')
    await button('发布').trigger('click'); await flushPromises()
    expect(cfg.api.update).toHaveBeenCalledWith('draft', expect.objectContaining({ name: '未保存名称', version: 7 }))
    expect(cfg.api.publish).toHaveBeenCalledWith('draft', 8)
    expect(vi.mocked(cfg.api.update).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(cfg.api.publish).mock.invocationCallOrder[0]!)
    expect(wrapper.get('input').element.value).toBe('未保存名称')
    expect(button('发布')?.attributes('disabled') !== undefined || !button('发布')).toBe(true)
    wrapper.unmount()
  })
  it(`${cfg.name}：保存失败保留输入并终止发布`, async () => {
    const { wrapper, button } = await harness()
    await wrapper.get('input').setValue('未保存名称')
    vi.mocked(cfg.api.update).mockRejectedValueOnce(new Error('版本冲突'))
    await button('发布').trigger('click'); await flushPromises()
    expect(cfg.api.publish).not.toHaveBeenCalled()
    expect(wrapper.get('input').element.value).toBe('未保存名称')
    wrapper.unmount()
  })
  it(`${cfg.name}：取消新建或离开时保留草稿，后续页可查询`, async () => {
    const { wrapper, button, router } = await harness()
    await wrapper.get('input').setValue('未保存名称')
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
    await button('新建草稿').trigger('click'); await flushPromises()
    expect(wrapper.get('input').element.value).toBe('未保存名称')
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/edit')
    await wrapper.get('.el-pagination .btn-next').trigger('click'); await flushPromises()
    expect(cfg.api.list).toHaveBeenLastCalledWith({ page: 2, page_size: 20 })
    wrapper.unmount()
  })
}
