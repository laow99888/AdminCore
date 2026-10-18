import { beforeEach, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { appointmentsApi } from '../src/api/organization'
import { useAuthStore } from '../src/stores/auth'
import { useTenantStore } from '../src/stores/tenants'
import { useSidebar } from '../src/composables/useSidebar'
import Appointments from '../src/components/common/OrganizationAppointments.vue'
import Designer from '../src/views/approvals/ApprovalFlowDesignerView.vue'
import { approvalFlowsApi } from '../src/api'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api/organization', () => ({ appointmentsApi: { list: vi.fn(), create: vi.fn(), finish: vi.fn() } }))
vi.mock('../src/api', () => ({ approvalFlowsApi: { list: vi.fn(), update: vi.fn() } }))
vi.mock('../src/components/common/PersonPicker.vue', () => ({ default: defineComponent({ props: ['disabled'], emits: ['update:modelValue'], template: `<button :disabled="disabled" @click="$emit('update:modelValue', { id: 'person',username: 'worker',display_name: 'Worker' })">选择人员</button>` }) }))
const Card = defineComponent({ template: '<section><slot name="header" /><slot /></section>' })
vi.mock('../src/components', () => ({ BaseCard: defineComponent({ template: '<section><slot name="header" /><slot /></section>' }), BaseButton: defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }) }))
vi.mock('../src/components/layout/AppLayout.vue', () => ({ default: defineComponent({ template: '<main><slot /></main>' }) }))
const Dialog = defineComponent({ props: ['modelValue','confirmDisabled'], emits: ['confirm','update:modelValue'], template: '<section v-if="modelValue" class="dialog"><slot /><button @click="$emit(\'update:modelValue\', false)">取消</button><button :disabled="confirmDisabled" @click="$emit(\'confirm\')">确认</button></section>' })
const Table = defineComponent({ props: ['data'], template: '<table><tbody><tr v-for="row in data" :key="row.id"><td>{{ row.username }}</td><td><slot name="actions" :row="row" /></td></tr></tbody></table>' })
const item = { id: 'a', user: 'person', username: 'worker', department: 'department', department_name: '采购', kind: 'primary' as const, starts_on: '2020-01-01', ends_on: null, cancelled: false, reason: '任命', version: 3, status: 'active' as const }
const page = (items = [item]) => ({ items, pagination: { page: 1,page_size: 20,total: items.length,total_pages: 1 } })
beforeEach(() => { vi.resetAllMocks(); useSidebar().isMobile.value = false; vi.mocked(appointmentsApi.list).mockResolvedValue(page()); vi.mocked(appointmentsApi.create).mockResolvedValue({} as never); vi.mocked(appointmentsApi.finish).mockResolvedValue({} as never) })
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(value => value.text() === text)!
async function setup() {
  const pinia = createPinia(), auth = useAuthStore(pinia)
  auth.token = 'isolated-test'; auth.user = { id: 'admin', username: 'admin',email: '',avatar: '',is_staff: true,permissions: ['*'] }
  const router = createRouter({ history: createMemoryHistory(),routes: [{ path: '/organization',component: { template: '<div />' } }] }); await router.push('/organization')
  const wrapper = mount(Appointments,{ props: { departments: [{ id: 'department',name: '采购',parent: null,order: 0,is_active: true,version: 1 }],referencesReady: true },global: { plugins: [pinia,router,ElementPlus],stubs: { BaseCard: Card,BaseDialog: Dialog,BaseTable: Table } } })
  await flushPromises(); return { wrapper,pinia,auth }
}

it('创建主兼职任职并按日期查询历史，日期清空后恢复完整历史', async () => {
  const { wrapper } = await setup()
  await button(wrapper,'新增任职').trigger('click'); await button(wrapper,'选择人员').trigger('click')
  await wrapper.get('.dialog select').setValue('department'); await wrapper.findAll('.dialog select')[1].setValue('secondary')
  await wrapper.get('.dialog input[type=date]').setValue('2026-10-18'); await wrapper.get('textarea').setValue('兼任采购')
  await button(wrapper,'确认').trigger('click'); await flushPromises()
  expect(appointmentsApi.create).toHaveBeenCalledWith(expect.objectContaining({ user: 'person',department: 'department',kind: 'secondary',starts_on: '2026-10-18',ends_on: null,version: 0 }))
  await wrapper.get('.filters input[type=date]').setValue('2026-10-19'); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(appointmentsApi.list).toHaveBeenLastCalledWith({ page: 1,page_size: 20,as_of: '2026-10-19' })
  await button(wrapper,'全部历史').trigger('click'); await flushPromises()
  expect(appointmentsApi.list).toHaveBeenLastCalledWith({ page: 1,page_size: 20 }); wrapper.unmount()
})

it('手机收窄固定操作列，切回桌面恢复宽度', async () => {
  const { wrapper } = await setup()
  useSidebar().isMobile.value = true; await flushPromises()
  expect(wrapper.findComponent(Table).attributes('action-width')).toBe('100')
  useSidebar().isMobile.value = false; await flushPromises()
  expect(wrapper.findComponent(Table).attributes('action-width')).toBe('190'); wrapper.unmount()
})

it('关闭任职弹窗仍保留原历史列表和分页结果', async () => {
  const { wrapper } = await setup()
  await button(wrapper,'新增任职').trigger('click'); await button(wrapper,'取消').trigger('click'); await flushPromises()
  expect(wrapper.find('.dialog').exists()).toBe(false)
  expect(wrapper.get('tbody').text()).toContain('worker')
  expect(appointmentsApi.list).toHaveBeenCalledTimes(1); wrapper.unmount()
})

it('结束任期携带原版本；冲突保留输入，不静默覆盖历史', async () => {
  const { wrapper } = await setup()
  vi.mocked(appointmentsApi.finish).mockRejectedValue({ response: { status: 409 } })
  await button(wrapper,'结束任期').trigger('click'); await wrapper.get('.dialog input').setValue('2026-10-20'); await wrapper.get('textarea').setValue('调岗')
  await button(wrapper,'确认').trigger('click'); await flushPromises()
  expect(appointmentsApi.finish).toHaveBeenCalledWith('a','end',{ version: 3,ends_on: '2026-10-20',reason: '调岗' })
  expect(wrapper.get('textarea').element.value).toBe('调岗'); expect(wrapper.get('.dialog [role=alert]').text()).toContain('任职已变化'); wrapper.unmount()
})

it('无权限不能新增或结束，当前任职不能取消计划', async () => {
  // 即使浏览器日期与服务端不同，入口也遵从服务器返回的状态。
  vi.mocked(appointmentsApi.list).mockResolvedValueOnce(page([{ ...item,starts_on: '2999-01-01' }]))
  const { wrapper,auth } = await setup()
  expect(button(wrapper,'取消计划').attributes('disabled')).toBeDefined()
  auth.user = { ...auth.user!,is_staff: false,permissions: [] }; await flushPromises()
  expect(button(wrapper,'新增任职').attributes('disabled')).toBeDefined()
  await button(wrapper,'新增任职').trigger('click'); expect(wrapper.find('.dialog').exists()).toBe(false)
  expect(appointmentsApi.create).not.toHaveBeenCalled(); wrapper.unmount()
})

it('列表加载失败可重试，切换租户后忽略旧响应', async () => {
  const { wrapper,pinia } = await setup()
  vi.mocked(appointmentsApi.list).mockRejectedValueOnce(new Error('连接中断'))
  await button(wrapper,'全部历史').trigger('click'); await flushPromises()
  expect(wrapper.findAll('[role=alert]').some(node => node.text().includes('连接中断'))).toBe(true)
  let finish!: (value: ReturnType<typeof page>) => void
  vi.mocked(appointmentsApi.list).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  await button(wrapper,'重试').trigger('click'); await flushPromises()
  useTenantStore(pinia).currentId = 'other'; await flushPromises()
  finish(page([{ ...item,username: '旧租户数据' }])); await flushPromises()
  expect(wrapper.text()).not.toContain('旧租户数据'); wrapper.unmount()
})

it('主管流程编辑与保存保留层级，不混入旧角色或固定人员字段', async () => {
  const pinia = createPinia(), auth = useAuthStore(pinia); auth.token = 'test'; auth.user = { id: 'admin',username: 'admin',email: '',avatar: '',is_staff: true,permissions: ['*'] }
  const router = createRouter({ history: createMemoryHistory(),routes: [{ path: '/edit',component: { template: '<div />' } }] }); await router.push('/edit')
  const flow = { id: 'flow',name: '主管',code: 'leader',status: 'draft' as const,version: 2,definition: { schema_version: 2 as const,inputs: [],nodes: [{ id: 'start',type: 'start' },{ id: 'review',type: 'user',assignee: { source: 'department_leader',levels: 2 } },{ id: 'end',type: 'end' }],edges: [{ from: 'start',to: 'review' },{ from: 'review',to: 'end' }] } }
  vi.mocked(approvalFlowsApi.list).mockResolvedValue({ items: [flow],pagination: { page: 1,page_size: 20,total: 1,total_pages: 1 } })
  vi.mocked(approvalFlowsApi.update).mockResolvedValue({ data: { data: { ...flow,version: 3 } } } as never)
  const wrapper = mount(Designer,{ global: { plugins: [pinia,router,ElementPlus] } }); await flushPromises()
  await wrapper.get('tbody tr').trigger('click'); await flushPromises()
  expect(wrapper.get<HTMLInputElement>('input[aria-label="主管层级"]').element.value).toBe('2')
  await button(wrapper,'保存草稿').trigger('click'); await flushPromises()
  const node = vi.mocked(approvalFlowsApi.update).mock.calls[0][1].definition.nodes[1]
  expect(node.assignee).toEqual({ source: 'department_leader',levels: 2 }); expect(node.assignee_ids).toBeUndefined(); wrapper.unmount()
})
