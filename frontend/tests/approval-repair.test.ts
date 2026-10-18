import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import { approvalsApi, type ApprovalRow } from '../src/api'
import { approvalDiagnosticsApi } from '../src/api/approvalDiagnostics'
import { useAuthStore } from '../src/stores/auth'
import List from '../src/views/approvals/ApprovalListView.vue'
vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api', () => ({ approvalsApi: { list: vi.fn(), repairStep: vi.fn() }, approvalFlowsApi: {}, newIdempotencyKey: vi.fn() }))
vi.mock('../src/api/approvalDiagnostics', () => ({ approvalDiagnosticsApi: { repairLegacy: vi.fn() } }))
vi.mock('../src/api/request', () => ({ notifyError: vi.fn() }))
vi.mock('../src/stores/modules', () => ({ useModuleStore: () => ({ enabled: () => true, config: {} }) }))
const Layout = defineComponent({ template: '<main><slot name="header" /><slot /></main>' })
const Table = defineComponent({ props: ['data'], template: '<div><slot v-for="row in data" name="actions" :row="row" /></div>' })
const Dialog = defineComponent({ props: ['modelValue', 'loading', 'title'], emits: ['confirm'], template: '<div v-if="modelValue" role="dialog"><h2>{{ title }}</h2><slot /><button :disabled="loading" @click="$emit(\'confirm\')">确认操作</button></div>' })
const Person = defineComponent({ emits: ['update:modelValue'], template: '<button @click="$emit(\'update:modelValue\', { id: \'target\', username: \'目标\' })">选择有效人员</button>' })
const legacy: ApprovalRow = { id: 'application', title: '旧单', request_type: 'other', content: '内容', applicant_name: '申请人', assignee_name: '已离职', status: 'pending', decision_comment: '', created_at: '', workflow_version: 4, flow: null, steps: [] }
beforeEach(() => vi.resetAllMocks())
afterEach(() => localStorage.clear())
async function setup(row: ApprovalRow) {
 vi.mocked(approvalsApi.list).mockResolvedValue({ items: [row], pagination: { total: 1 } } as never)
 const pinia = createPinia(), auth = useAuthStore(pinia)
 auth.token = 'repair'; auth.user = { id: 'admin', username: 'admin', email: '', avatar: '', is_staff: true, permissions: ['*'] }
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Layout }] }); await router.push('/')
 const wrapper = mount(List, { global: { plugins: [pinia, router, ElementPlus], stubs: { AppLayout: Layout, BaseCard: Layout, BaseTable: Table, BaseDialog: Dialog, PersonPicker: Person, ApprovalDiagnostics: true, ApprovalOperations: true } } })
 await flushPromises()
 await wrapper.getComponent({ name: 'ElTabs' }).vm.$emit('update:modelValue', 'exceptions')
 await flushPromises()
 const button = (text: string) => wrapper.findAll('button').find(node => node.text() === text)!
 await button('详情').trigger('click'); await button('修复审批人').trigger('click'); await flushPromises()
 await button('选择有效人员').trigger('click')
 return { wrapper, button }
}
it('旧版单人审批修复传流程版本，不要求不存在的步骤', async () => {
 vi.mocked(approvalDiagnosticsApi.repairLegacy).mockResolvedValue({ data: { data: { ...legacy, workflow_version: 5 } } } as never)
 const { wrapper } = await setup(legacy)
 expect(wrapper.text()).not.toContain('待处理步骤')
 const dialog = wrapper.findAll('[role="dialog"]').find(node => node.find('h2').text() === '修复审批人')!
 await dialog.get('button:last-child').trigger('click'); await flushPromises()
 expect(approvalDiagnosticsApi.repairLegacy).toHaveBeenCalledWith('application', 'target', 4, '')
 expect(approvalsApi.repairStep).not.toHaveBeenCalled()
 wrapper.unmount()
})
it('流程修复仍发送当前步骤版本，冲突时保留修复表单', async () => {
 const flow = { ...legacy, flow: 'flow', steps: [{ id: 'step', node_key: 'review', kind: 'user', mode: 'all', sequence: 1, status: 'pending', version: 7 }] } as ApprovalRow
 vi.mocked(approvalsApi.repairStep).mockRejectedValue(new Error('409'))
 const { wrapper } = await setup(flow)
 expect(wrapper.text()).toContain('待处理步骤')
 const dialog = wrapper.findAll('[role="dialog"]').find(node => node.find('h2').text() === '修复审批人')!
 await dialog.get('textarea').setValue('保留改派原因')
 await dialog.get('button:last-child').trigger('click'); await flushPromises()
 expect(approvalsApi.repairStep).toHaveBeenCalledWith('application', 'target', 'step', 7, '保留改派原因')
 expect(wrapper.findAll('[role="dialog"]').some(node => node.find('h2').text() === '修复审批人')).toBe(true)
 expect(dialog.get('textarea').element.value).toBe('保留改派原因')
 expect(approvalDiagnosticsApi.repairLegacy).not.toHaveBeenCalled()
 wrapper.unmount()
})
