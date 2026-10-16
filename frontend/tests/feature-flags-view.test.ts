import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { featureFlagsApi } from '../src/api/featureFlags'
import FeatureFlagsView from '../src/views/system/FeatureFlagsView.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api/featureFlags', () => ({ featureFlagsApi: { list: vi.fn(), detail: vi.fn(), save: vi.fn(), targets: vi.fn(), remove: vi.fn() } }))
vi.mock('../src/components', () => ({
  AppLayout: defineComponent({ template: '<main><slot /></main>' }),
  BaseCard: defineComponent({ template: '<section><slot name="header" /><slot /></section>' }),
  BaseButton: defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }),
  BaseTable: defineComponent({ name: 'TableFixture', props: ['data'], emits: ['update:currentPage', 'update:pageSize'], template: '<div><div v-for="row in data" :key="row.id"><slot name="actions" :row="row" /></div></div>' }),
  BaseDialog: defineComponent({ props: ['modelValue', 'loading', 'confirmDisabled'], emits: ['confirm', 'update:modelValue'], template: '<section v-if="modelValue" role="dialog"><slot /><button data-save :disabled="loading || confirmDisabled" @click="$emit(\'confirm\')">submit</button></section>' }),
}))
const stubs = {
  'el-button': defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }),
  'el-input': defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' }),
  'el-form': defineComponent({ template: '<form><slot /></form>' }),
  'el-form-item': defineComponent({ template: '<div><slot /></div>' }),
  'el-input-number': true, 'el-select': true, 'el-option': true, 'el-switch': true,
}
const row = { id: 'f1', key: 'checkout.new', name: 'original', description: '', enabled: false, rollout: 0, included_users: [], excluded_users: [], roles: [], version: 1, created_at: '', updated_at: '' }
let mounted: VueWrapper | undefined
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find(item => item.text() === text)!
async function setup() {
  const pinia = createPinia(), auth = useAuthStore(pinia), modules = useModuleStore(pinia)
  auth.token = 'unit-fixture'; auth.applyUser({ id: 'actor', username: 'actor', email: '', avatar: '', is_staff: true, permissions: ['*'] })
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'feature_flags', title: 'flags', enabled: true, paths: ['/system/feature-flags'], dependencies: [] }] }
  const router = createRouter({ history: createMemoryHistory(), routes: ['/system/feature-flags', '/login'].map(path => ({ path, component: { template: '<div />' } })) })
  await router.push('/system/feature-flags'); await router.isReady()
  vi.mocked(featureFlagsApi.list).mockResolvedValue({ items: [row], pagination: { page: 1, page_size: 10, total: 1, total_pages: 1 } })
  vi.mocked(featureFlagsApi.targets).mockResolvedValue([])
  vi.mocked(featureFlagsApi.detail).mockResolvedValue({ ...row, name: 'server latest', version: 2 })
  mounted = mount(FeatureFlagsView, { global: { plugins: [pinia, router], stubs } })
  await flushPromises()
  return { wrapper: mounted, auth, modules }
}
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); sessionStorage.clear() })
afterEach(() => { mounted?.unmount(); mounted = undefined })

it('服务端冲突保留草稿，查看不覆盖，显式应用后携带最新版本保存', async () => {
  const { wrapper } = await setup()
  vi.mocked(featureFlagsApi.save).mockRejectedValueOnce({ response: { status: 409 } }).mockResolvedValue({} as any)
  await button(wrapper, '编辑').trigger('click'); await flushPromises()
  const input = () => wrapper.get<HTMLInputElement>('input[aria-label="名称"]')
  await input().setValue('draft'); await wrapper.get('[data-save]').trigger('click'); await flushPromises()
  expect(input().element.value).toBe('draft'); expect(wrapper.get('[data-save]').attributes('disabled')).toBeDefined()
  await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
  expect(wrapper.get('table').text()).toContain('server latest'); expect(input().element.value).toBe('draft')
  await button(wrapper, '载入服务器最新值（替换当前输入）').trigger('click'); await flushPromises()
  expect(input().element.value).toBe('server latest')
  await wrapper.get('[data-save]').trigger('click'); await flushPromises()
  expect(vi.mocked(featureFlagsApi.save).mock.calls[0]![1]).toMatchObject({ version: 1, name: 'draft' })
  expect(vi.mocked(featureFlagsApi.save).mock.calls[1]![1]).toMatchObject({ version: 2, name: 'server latest' })
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
})
it.each(['permission', 'module', 'unmount'])('%s 变化中止目标读取，迟到数据不回填', async action => {
  const { wrapper, auth, modules } = await setup()
  let complete!: (value: any) => void
  vi.mocked(featureFlagsApi.targets).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  await button(wrapper, '编辑').trigger('click')
  const signal = vi.mocked(featureFlagsApi.targets).mock.calls[0]![3]!
  if (action === 'permission') auth.applyUser({ ...auth.user!, permissions: [] })
  if (action === 'module') modules.config!.modules[0]!.enabled = false
  if (action === 'unmount') { wrapper.unmount(); mounted = undefined }
  await flushPromises(); expect(signal.aborted).toBe(true)
  complete([{ id: 'late', label: 'late private name' }]); await flushPromises()
  expect(wrapper.text()).not.toContain('late private name'); expect(featureFlagsApi.save).not.toHaveBeenCalled()
  if (action !== 'unmount') expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
})
it('分页与每页容量使用通用表格实际事件；读权限不能创建', async () => {
  const { wrapper, auth } = await setup()
  const table = wrapper.findComponent({ name: 'TableFixture' })
  table.vm.$emit('update:currentPage', 2); await flushPromises()
  expect(featureFlagsApi.list).toHaveBeenLastCalledWith({ page: 2, page_size: 10, search: '' }, expect.any(AbortSignal))
  table.vm.$emit('update:pageSize', 20); await flushPromises()
  expect(featureFlagsApi.list).toHaveBeenLastCalledWith({ page: 1, page_size: 20, search: '' }, expect.any(AbortSignal))
  auth.applyUser({ ...auth.user!, permissions: ['feature_flag:read'] }); await flushPromises()
  expect(wrapper.findAll('button').some(item => item.text() === '新增开关')).toBe(false)
  expect(wrapper.findAll('button').some(item => item.text() === '编辑')).toBe(false)
})
