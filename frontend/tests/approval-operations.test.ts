import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { useAuthStore } from '../src/stores/auth'
import { approvalsApi, type ApprovalRow } from '../src/api'
import { notifyError } from '../src/api/request'
import Operations from '../src/views/approvals/ApprovalOperations.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api', () => ({ approvalsApi: { history: vi.fn(), returnNode: vi.fn(), retryTimeout: vi.fn() }, newIdempotencyKey: () => 'return-stable-key' }))
vi.mock('../src/api/request', () => ({ notifyError: vi.fn() }))
const Dialog = defineComponent({ props: ['modelValue', 'loading', 'title'], emits: ['confirm'], template: '<div v-if="modelValue" role="dialog"><h2>{{ title }}</h2><slot /><button :disabled="loading" @click="$emit(\'confirm\')">确认操作</button></div>' })
const base: ApprovalRow = { id: 'app', title: '采购', request_type: 'purchase', content: '说明', applicant_name: '申请人', assignee_name: '审核人', status: 'pending', decision_comment: '', created_at: '', flow: 'flow', flow_revision: 2, workflow_version: 7, return_count: 0, returnable_nodes: ['first'], steps: [{ id: 'step', node_key: 'second', kind: 'user', mode: 'all', sequence: 1, status: 'pending', assignee: 'actor', version: 3 }] }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(approvalsApi.history).mockResolvedValue({ items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 } })
})
afterEach(() => { localStorage.clear() })
async function setup(application = base, isAdmin = false, actor = 'actor') {
  const pinia = createPinia(), auth = useAuthStore(pinia)
  auth.token = 'operations'; auth.user = { id: actor, username: actor, email: '', avatar: '', permissions: ['*'], is_staff: isAdmin }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
  await router.push('/')
  const wrapper = mount(Operations, { props: { application }, global: { plugins: [pinia, router, ElementPlus], stubs: { BaseDialog: Dialog, PersonPicker: true } } })
  await flushPromises()
  const button = (text: string) => wrapper.findAll('button').find(node => node.text() === text)!
  return { wrapper, auth, button }
}
it('退回提交包含当前流程版本、目标和原因，成功刷新历史并发出新申请', async () => {
  const returned = { ...base, return_count: 1, workflow_version: 8 }
  vi.mocked(approvalsApi.returnNode).mockResolvedValue({ data: { data: returned } } as never)
  const { wrapper, button } = await setup()
  await button('退回指定节点').trigger('click'); await flushPromises()
  await wrapper.get('textarea').setValue('请重新核实')
  await button('确认操作').trigger('click'); await flushPromises()
  expect(approvalsApi.returnNode).toHaveBeenCalledWith('app', 'first', 7, '请重新核实', 'return-stable-key')
  expect(wrapper.emitted('changed')?.[0]).toEqual([returned])
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(approvalsApi.history).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})
it('版本冲突保留目标和原因；同一份输入重试使用相同幂等键', async () => {
  vi.mocked(approvalsApi.returnNode).mockRejectedValue(new Error('409'))
  const { wrapper, button } = await setup()
  await button('退回指定节点').trigger('click'); await flushPromises()
  await wrapper.get('textarea').setValue('保留我的原因')
  await button('确认操作').trigger('click'); await flushPromises()
  expect(wrapper.get('textarea').element.value).toBe('保留我的原因')
  await button('确认操作').trigger('click'); await flushPromises()
  expect(approvalsApi.returnNode).toHaveBeenCalledTimes(2)
  expect(vi.mocked(approvalsApi.returnNode).mock.calls[0]).toEqual(vi.mocked(approvalsApi.returnNode).mock.calls[1])
  expect(notifyError).toHaveBeenCalled()
  expect(wrapper.emitted('changed')).toBeUndefined()
  wrapper.unmount()
})
it('空原因不请求接口；非当前审批人和已结束流程没有退回入口', async () => {
  const own = await setup()
  await own.button('退回指定节点').trigger('click'); await flushPromises()
  await own.button('确认操作').trigger('click'); await flushPromises()
  expect(approvalsApi.returnNode).not.toHaveBeenCalled(); own.wrapper.unmount()
  const stranger = await setup(base, true, 'admin-other')
  expect(stranger.button('退回指定节点')).toBeUndefined(); stranger.wrapper.unmount()
  const ended = await setup({ ...base, status: 'approved' })
  expect(ended.button('退回指定节点')).toBeUndefined(); ended.wrapper.unmount()
})
it('管理员只重试异常提醒，显示队列受理而非已送达，提交步骤版本和原因', async () => {
  const application = { ...base, steps: [{ ...base.steps![0]!, due_at: '2026-10-18T12:00:00+08:00', timeout_error: 'remind', reminded_at: '2026-10-18T12:01:00+08:00' }] }
  vi.mocked(approvalsApi.retryTimeout).mockResolvedValue({ data: { data: base } } as never)
  const { wrapper, button } = await setup(application, true)
  expect(wrapper.text()).toContain('超时通知接收人异常')
  await button('修复并重试提醒').trigger('click'); await flushPromises()
  await wrapper.get('textarea').setValue('已恢复账号')
  await button('确认操作').trigger('click'); await flushPromises()
  expect(approvalsApi.retryTimeout).toHaveBeenCalledWith('app', 'step', 3, '已恢复账号', undefined)
  wrapper.unmount()
})
it('迟到的历史结果不进入退出后的页面，错误有重试入口', async () => {
  vi.mocked(approvalsApi.history).mockRejectedValueOnce(new Error('network'))
  const { wrapper, button, auth } = await setup()
  expect(wrapper.text()).toContain('操作记录加载失败，请重试')
  let resolve!: (value: unknown) => void
  vi.mocked(approvalsApi.history).mockReturnValueOnce(new Promise(done => { resolve = done }) as never)
  await button('刷新').trigger('click')
  auth.token = ''; auth.user = null
  resolve({ items: [{ id: 'old', action: 'return', comment: '旧会话原因', metadata: {} }], pagination: { total: 1 } }); await flushPromises()
  expect(wrapper.text()).not.toContain('旧会话原因')
  wrapper.unmount()
})
