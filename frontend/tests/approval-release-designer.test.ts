import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { useAuthStore } from '../src/stores/auth'
import { approvalFlowsApi, type ApprovalFlowRow } from '../src/api'
import Designer from '../src/views/approvals/ApprovalFlowDesignerView.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api', () => ({ approvalFlowsApi: { list: vi.fn(), newRevision: vi.fn(), update: vi.fn(), publish: vi.fn(), archive: vi.fn() } }))
vi.mock('../src/components/layout/AppLayout.vue', () => ({ default: defineComponent({ template: '<main><slot /></main>' }) }))
vi.mock('../src/components/common/PersonPicker.vue', () => ({ default: defineComponent({ props: ['modelValue', 'disabled'], template: '<button :disabled="disabled">选择升级人员</button>' }) }))
const row: ApprovalFlowRow = { id: 'release', name: '采购', code: 'purchase', version: 7, revision: 2, status: 'draft', definition: { schema_version: 2, inputs: [], nodes: [
  { id: 'start', type: 'start' }, { id: 'review', type: 'user', assignee_ids: ['reviewer'], timeout: { minutes: 60, escalate_after_minutes: 120, escalate_to: 'escalation' } }, { id: 'end', type: 'end' },
], edges: [{ from: 'start', to: 'review' }, { from: 'review', to: 'end' }] } }
beforeEach(() => vi.resetAllMocks())
afterEach(() => { localStorage.clear() })
async function setup(flow = row) {
  vi.mocked(approvalFlowsApi.list).mockResolvedValue({ items: [flow], pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 } })
  const pinia = createPinia(), auth = useAuthStore(pinia)
  auth.token = 'release-editor'; auth.user = { id: 'admin', username: 'admin', email: '', avatar: '', is_staff: true, permissions: ['*'] }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] }); await router.push('/')
  const wrapper = mount(Designer, { global: { plugins: [pinia, router, ElementPlus] } })
  await flushPromises(); await wrapper.get('tbody tr').trigger('click'); await flushPromises()
  const button = (text: string) => wrapper.findAll('button').find(node => node.text() === text)!
  return { wrapper, auth, button }
}
it('编辑保存保留节点时限和升级人员，版次与编辑版本分别显示', async () => {
  vi.mocked(approvalFlowsApi.update).mockResolvedValue({ data: { data: { ...row, version: 8 } } } as never)
  const { wrapper, button } = await setup()
  expect(wrapper.text()).toContain('v2'); expect(wrapper.text()).toContain('发布版次')
  await button('保存草稿').trigger('click'); await flushPromises()
  expect(approvalFlowsApi.update).toHaveBeenCalledWith('release', expect.objectContaining({ version: 7, definition: expect.objectContaining({ nodes: expect.arrayContaining([expect.objectContaining({ timeout: { minutes: 60, escalate_after_minutes: 120, escalate_to: 'escalation' } })]) }) }))
  wrapper.unmount()
})
it('新建版本只产生草稿，发布需显式操作；失败不清空旧版详情', async () => {
  const { wrapper, button } = await setup({ ...row, status: 'published' })
  vi.mocked(approvalFlowsApi.newRevision).mockRejectedValueOnce(new Error('已有草稿'))
  await button('新建版本').trigger('click'); await flushPromises()
  expect(button('新建版本')).toBeTruthy(); expect(approvalFlowsApi.publish).not.toHaveBeenCalled()
  vi.mocked(approvalFlowsApi.newRevision).mockResolvedValueOnce({ data: { data: { ...row, id: 'new-release', version: 1, revision: 3 } } } as never)
  await button('新建版本').trigger('click'); await flushPromises()
  expect(button('发布')).toBeTruthy(); expect(approvalFlowsApi.publish).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('离开会话后返回的新版本响应不恢复旧编辑器', async () => {
  let resolve!: (value: unknown) => void
  vi.mocked(approvalFlowsApi.newRevision).mockReturnValue(new Promise(done => { resolve = done }) as never)
  const { wrapper, button, auth } = await setup({ ...row, status: 'published' })
  await button('新建版本').trigger('click'); await flushPromises()
  auth.user = null; auth.token = ''
  resolve({ data: { data: { ...row, id: 'new-release' } } }); await flushPromises()
  expect(wrapper.find('.editor-card').exists()).toBe(false)
  wrapper.unmount()
})

it('工作日历保存完整往返；已发布版本不可修改日历', async () => {
 const calendar = { timezone: 'Asia/Shanghai', weekdays: [1, 2, 3, 4, 5], start: '09:00', end: '18:00', closed_dates: ['2026-10-01'], extra_dates: ['2026-10-10'] }
 const flow = structuredClone(row)
 const node = (flow.definition.nodes as Array<Record<string, unknown>>)[1]!
 node.timeout = { minutes: 60, escalate_after_minutes: 120, escalate_to: 'escalation', calendar }
 vi.mocked(approvalFlowsApi.update).mockResolvedValue({ data: { data: { ...flow, version: 8 } } } as never)
 const draft = await setup(flow)
 await draft.button('保存草稿').trigger('click'); await flushPromises()
 expect(approvalFlowsApi.update).toHaveBeenCalledWith('release', expect.objectContaining({ definition: expect.objectContaining({ nodes: expect.arrayContaining([expect.objectContaining({ timeout: expect.objectContaining({ calendar }) })]) }) }))
 draft.wrapper.unmount()
 const published = await setup({ ...flow, status: 'published' })
 expect((published.wrapper.get('input[aria-label="日历时区"]').element as HTMLInputElement).disabled).toBe(true)
 expect(published.button('保存草稿').attributes('disabled')).toBeDefined()
 published.wrapper.unmount()
})
