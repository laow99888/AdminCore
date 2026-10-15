import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { postsApi } from '../src/api/posts'
import { exampleApi } from '../src/api'
import PostManagementView from '../src/views/system/PostManagementView.vue'
import WorkItemListView from '../src/views/example/WorkItemListView.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/composables/usePageState', () => ({ usePageState: vi.fn() }))
vi.mock('../src/api/posts', () => ({ postsApi: { list: vi.fn(), detail: vi.fn(), save: vi.fn(), choices: vi.fn(), assign: vi.fn(), remove: vi.fn() } }))
vi.mock('../src/api', async original => ({ ...await original<typeof import('../src/api')>(), exampleApi: { list: vi.fn(), detail: vi.fn(), save: vi.fn(), remove: vi.fn() } }))
vi.mock('../src/components/layout/AppLayout.vue', () => ({ default: defineComponent({ template: '<main><slot /></main>' }) }))
vi.mock('../src/components', () => ({
  AppLayout: defineComponent({ template: '<main><slot /></main>' }),
  BaseCard: defineComponent({ template: '<section><slot name="header" /><slot /></section>' }),
  BaseButton: defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }),
  BaseTable: defineComponent({ props: ['data'], template: '<div><div v-for="row in data" :key="row.id"><slot name="actions" :row="row" /></div></div>' }),
  BaseDialog: defineComponent({ name: 'DialogFixture', props: ['modelValue', 'loading', 'confirmDisabled'], emits: ['confirm', 'update:modelValue'], template: '<section v-if="modelValue" role="dialog"><slot /><button data-save :disabled="loading || confirmDisabled" @click="$emit(\'confirm\')">submit fixture</button><button data-close @click="$emit(\'update:modelValue\', false)">close fixture</button></section>' }),
}))
const stubs = {
  DataImportButton: true, PersonPicker: true,
  'el-button': defineComponent({ props: ['disabled', 'loading'], template: '<button :disabled="disabled || loading"><slot /></button>' }),
  'el-input': defineComponent({ inheritAttrs: true, props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' }),
  'el-form': defineComponent({ template: '<form><slot /></form>' }),
  'el-form-item': defineComponent({ template: '<div><slot /></div>' }),
  'el-alert': defineComponent({ props: ['title'], template: '<p role="alert">{{ title }}</p>' }),
  'el-tabs': defineComponent({ emits: ['update:modelValue', 'tab-change'], template: '<div><button data-section @click="$emit(\'update:modelValue\', \'user-posts\'); $emit(\'tab-change\')">人员任职</button><slot /></div>' }),
  'el-tab-pane': true, 'el-input-number': true, 'el-switch': true, 'el-select': true, 'el-option': true,
}
const post = { id: 'p1', code: 'editor', name: 'original', description: 'original notes', order: 0, is_active: true, version: 1 }
const example = { id: 'e1', title: 'original', notes: 'original notes', status: 'open' as const, priority: 'normal' as const, creator: 'actor', creator_name: 'actor', version: 1, created_at: '' }
const cases = [
  { kind: 'posts', route: '/organization/posts', component: PostManagementView, api: postsApi, row: post, field: 'name', label: '岗位名称', module: 'organization' },
  { kind: 'example', route: '/example', component: WorkItemListView, api: exampleApi, row: example, field: 'title', label: '工单标题', module: 'example' },
] as const
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find(item => item.text() === text)!
async function setup(item: typeof cases[number]) {
  const pinia = createPinia(), auth = useAuthStore(pinia), modules = useModuleStore(pinia)
  auth.token = 'isolated-unit-token'; auth.applyUser({ id: 'actor', username: 'actor', email: '', avatar: '', is_staff: true, permissions: ['*'] })
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: item.module, title: 'fixture', enabled: true, paths: [item.route], dependencies: [] }] }
  const router = createRouter({ history: createMemoryHistory(), routes: [item.route, '/login'].map(path => ({ path, component: { template: '<div />' } })) })
  await router.push(item.route); await router.isReady()
  vi.mocked(item.api.list).mockResolvedValue({ items: [item.row] as any, pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } })
  vi.mocked(item.api.save).mockRejectedValueOnce({ response: { status: 409 } }).mockResolvedValue({} as any)
  vi.mocked(item.api.detail).mockResolvedValue({ ...item.row, [item.field]: 'server latest', version: 2 } as any)
  const wrapper = mount(item.component, { global: { plugins: [pinia, router], stubs } })
  await flushPromises(); await button(wrapper, '编辑').trigger('click')
  const input = () => wrapper.get<HTMLInputElement>(`input[aria-label="${item.label}"]`)
  await input().setValue('retained draft'); await wrapper.get('[data-save]').trigger('click'); await flushPromises()
  return { wrapper, auth, modules, input }
}
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear() })

for (const item of cases) describe(`${item.kind} 页面冲突契约`, () => {
  it('冲突和查看均不换草稿或版本，显式应用后才使用新版本提交', async () => {
    const { wrapper, input } = await setup(item)
    expect(wrapper.find('[role="region"]').exists()).toBe(true)
    expect(input().element.value).toBe('retained draft'); expect(item.api.detail).not.toHaveBeenCalled()
    expect(wrapper.get('[data-save]').attributes('disabled')).toBeDefined()
    wrapper.findComponent({ name: 'DialogFixture' }).vm.$emit('confirm'); await flushPromises()
    expect(item.api.save).toHaveBeenCalledTimes(1)
    await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
    expect(wrapper.get('table').text()).toContain('retained draft'); expect(wrapper.get('table').text()).toContain('server latest')
    expect(wrapper.findAll('tbody tr')).toHaveLength(item.kind === 'posts' ? 5 : 4)
    for (const label of item.kind === 'posts' ? ['岗位编码', '岗位名称', '岗位说明', '排序', '启用'] : ['工单标题', '工单说明', '工单状态', '优先级']) expect(wrapper.get('table').text()).toContain(label)
    expect(input().element.value).toBe('retained draft'); expect(item.api.save).toHaveBeenCalledTimes(1)
    expect(vi.mocked(item.api.detail).mock.calls[0]![1]).toBeInstanceOf(AbortSignal)
    await button(wrapper, '载入服务器最新值（替换当前输入）').trigger('click')
    expect(input().element.value).toBe('server latest'); expect(wrapper.find('[role="region"]').exists()).toBe(false)
    await input().setValue('reviewed'); await wrapper.get('[data-save]').trigger('click'); await flushPromises()
    expect(item.api.save).toHaveBeenCalledTimes(2)
    expect(vi.mocked(item.api.save).mock.calls[0]![1]).toMatchObject({ version: 1, [item.field]: 'retained draft' })
    expect(vi.mocked(item.api.save).mock.calls[1]![1]).toMatchObject({ version: 2, [item.field]: 'reviewed' })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
  it('服务器读取失败保留草稿，可重试且服务器 HTML 只作文本比较', async () => {
    const { wrapper, input } = await setup(item)
    vi.mocked(item.api.detail).mockRejectedValueOnce(new Error('403')).mockResolvedValueOnce({ ...item.row, [item.field]: '<img src=x onerror=alert(1)>', version: 3 } as any)
    await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('最新值加载失败或已无权限'); expect(input().element.value).toBe('retained draft')
    expect(wrapper.find('table').exists()).toBe(false)
    await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
    expect(wrapper.get('table').text()).toContain('<img src=x onerror=alert(1)>'); expect(wrapper.find('img').exists()).toBe(false)
    expect(input().element.value).toBe('retained draft'); expect(item.api.save).toHaveBeenCalledTimes(1)
  })
  it.each(['permission', 'module', 'unmount'])('%s 改变中止比较，迟到服务器快照不能回填', async action => {
    const { wrapper, auth, modules } = await setup(item)
    let complete!: (value: any) => void
    vi.mocked(item.api.detail).mockImplementationOnce(() => new Promise<any>(resolve => { complete = resolve }))
    await button(wrapper, '查看服务器最新值').trigger('click')
    const signal = vi.mocked(item.api.detail).mock.calls[0]![1]!
    if (action === 'permission') auth.applyUser({ ...auth.user!, permissions: [] })
    if (action === 'module') modules.config!.modules[0]!.enabled = false
    if (action === 'unmount') wrapper.unmount()
    expect(signal.aborted).toBe(true)
    complete({ ...item.row, [item.field]: 'late private value', version: 99 }); await flushPromises()
    expect(wrapper.text()).not.toContain('late private value'); expect(item.api.save).toHaveBeenCalledTimes(1)
    if (action !== 'unmount') expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
})

it('岗位切换到任职时取消服务器比较，不将岗位快照写入任职表单', async () => {
  const { wrapper } = await setup(cases[0])
  let complete!: (value: any) => void
  vi.mocked(postsApi.detail).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  await button(wrapper, '查看服务器最新值').trigger('click')
  const signal = vi.mocked(postsApi.detail).mock.calls[0]![1]!
  await wrapper.get('[data-section]').trigger('click'); expect(signal.aborted).toBe(true)
  complete({ ...post, name: 'late post', version: 4 }); await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false); expect(wrapper.text()).not.toContain('late post')
})
