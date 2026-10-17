import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import { approvalsApi } from '../src/api'
import { notifyError } from '../src/api/request'
import { useAuthStore } from '../src/stores/auth'
import ApprovalList from '../src/views/approvals/ApprovalListView.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value }))
vi.mock('../src/api', () => ({ approvalsApi: { list: vi.fn() }, approvalFlowsApi: {}, newIdempotencyKey: vi.fn() }))
vi.mock('../src/api/request', () => ({ notifyError: vi.fn() }))
vi.mock('../src/stores/modules', () => ({ useModuleStore: () => ({ enabled: () => true, config: {} }) }))
const Layout = defineComponent({ template: '<main><slot name="header" /><slot /></main>' })
const Table = defineComponent({ name: 'BaseTable', props: ['data', 'total', 'loading'], template: '<div />' })
beforeEach(() => vi.resetAllMocks())
afterEach(() => localStorage.clear())
async function setup() {
  const pinia = createPinia(), auth = useAuthStore(pinia)
  auth.token = 'approval-owner'; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: true, permissions: ['*'] }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Layout }] }); await router.push('/')
  const wrapper = mount(ApprovalList, { global: { plugins: [pinia, router, ElementPlus], stubs: {
    AppLayout: Layout, BaseCard: Layout, BaseTable: Table, BaseDialog: true, PersonPicker: true,
  } } })
  return { wrapper, auth, table: wrapper.getComponent(Table) }
}
it('审批页签列表请求失败会结束加载并显示受控错误', async () => {
  vi.mocked(approvalsApi.list).mockResolvedValue({ items: [], pagination: { total: 0 } } as never)
  const { wrapper, table } = await setup(); await flushPromises()
  const failure = new Error('network interrupted')
  vi.mocked(approvalsApi.list).mockRejectedValueOnce(failure)
  await wrapper.getComponent({ name: 'ElTabs' }).vm.$emit('tab-change', 'cc'); await flushPromises()
  expect(notifyError).toHaveBeenCalledWith(failure, '列表加载失败')
  expect(table.props('loading')).toBe(false)
  wrapper.unmount()
})
it('退出后返回的401被接住，不再提示旧会话错误或恢复旧列表', async () => {
  let reject!: (error: Error) => void
  vi.mocked(approvalsApi.list).mockReturnValue(new Promise((_resolve, fail) => { reject = fail }))
  const { wrapper, auth, table } = await setup()
  auth.user = null; auth.token = ''
  reject(new Error('Request failed with status code 401')); await flushPromises()
  expect(table.props('data')).toEqual([]); expect(table.props('loading')).toBe(false)
  expect(notifyError).not.toHaveBeenCalled()
  wrapper.unmount()
})
