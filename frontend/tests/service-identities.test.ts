import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
vi.mock('vue-router', async importOriginal => ({ ...await importOriginal<typeof import('vue-router')>(), onBeforeRouteLeave: vi.fn() }))
vi.mock('../src/api/serviceIdentities', () => ({ serviceIdentitiesApi: { list: vi.fn(), roles: vi.fn(), credentials: vi.fn(), create: vi.fn(), update: vi.fn(), issue: vi.fn(), rotate: vi.fn(), revoke: vi.fn() } }))
vi.mock('../src/api/apiCredentials', () => ({ apiCredentialsApi: { scopes: vi.fn() } }))
vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string) => text, registerUiMessages: vi.fn() }))
vi.mock('../src/components', () => ({
  BaseButton: defineComponent({ template: '<button><slot /></button>' }),
  BaseTable: defineComponent({ props: ['data'], template: '<div><article v-for="row in data" :key="row.id">{{ row.name }}<slot name="actions" :row="row" /></article></div>' }),
}))
import { serviceIdentitiesApi as api, type ServiceIdentity } from '../src/api/serviceIdentities'
import { apiCredentialsApi } from '../src/api/apiCredentials'
import ServiceIdentityPanel from '../src/components/integrations/ServiceIdentityPanel.vue'
import { useAuthStore } from '../src/stores/auth'
import { useTenantStore } from '../src/stores/tenants'

const row: ServiceIdentity = { id: 'machine', name: 'ERP identity', description: '', tenant_id: null, is_active: true, role_ids: ['reader'], version: 1, created_at: '' }
const result = { items: [row], pagination: { page: 1, page_size: 10, total: 1, total_pages: 1 } }
function harness(admin = true) {
  const auth = useAuthStore()
  auth.applyUser({ id: 'owner', username: 'owner', email: '', avatar: '', is_staff: admin, permissions: ['api_credential:manage'] })
  const wrapper = mount(ServiceIdentityPanel, { global: { stubs: {
    'el-card': defineComponent({ template: '<section><slot name="header" /><slot /></section>' }),
    'el-dialog': defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>' }),
    'el-alert': defineComponent({ props: ['title'], template: '<p role="alert">{{ title }}</p>' }),
    'el-form': defineComponent({ template: '<form><slot /></form>' }),
    'el-form-item': defineComponent({ template: '<div><slot /></div>' }),
    'el-input': true, 'el-input-number': true, 'el-checkbox-group': true,
    PasswordConfirmationDialog: true,
  } } })
  return { wrapper, auth }
}
describe('机器身份管理的权限与迟到响应', () => {
  beforeEach(() => {
    vi.resetAllMocks(); localStorage.clear(); localStorage.setItem('token', 'fixture-session'); setActivePinia(createPinia())
    vi.mocked(api.list).mockResolvedValue(result)
    vi.mocked(api.roles).mockResolvedValue([{ id: 'reader', name: 'Dedicated reader' }])
    vi.mocked(api.credentials).mockResolvedValue([])
    vi.mocked(apiCredentialsApi.scopes).mockResolvedValue([{ code: 'task:read', label: '任务查询' }])
  })
  it('普通成员即使持有管理能力也没有独立管理入口', async () => {
    const { wrapper } = harness(false); await flushPromises()
    expect(wrapper.text()).toBe(''); expect(api.list).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('展示身份和永久撤销语义，读取凭证不展示密钥', async () => {
    const { wrapper } = harness(); await flushPromises()
    expect(wrapper.text()).toContain('不受创建人改密或离职影响')
    await wrapper.findAll('button').find(button => button.text() === '管理机器凭证')!.trigger('click'); await flushPromises()
    expect(api.credentials).toHaveBeenCalledWith('machine', expect.any(AbortSignal))
    expect(wrapper.text()).toContain('重新启用后须重新签发')
    expect(wrapper.find('#service-identity-secret').exists()).toBe(false); wrapper.unmount()
  })
  it('失败可重试，没有合适角色时提示配置角色', async () => {
    vi.mocked(api.list).mockRejectedValueOnce(new Error('offline')); vi.mocked(api.roles).mockResolvedValue([])
    const { wrapper } = harness(); await flushPromises()
    expect(wrapper.text()).toContain('机器身份加载失败')
    await wrapper.findAll('button').find(button => button.text() === '刷新机器身份')!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('ERP identity'); expect(wrapper.text()).toContain('没有可授予的专用只读角色'); wrapper.unmount()
  })
  it('撤权中止列表请求，丢弃迟到结果', async () => {
    let finish!: (value: typeof result) => void
    vi.mocked(api.list).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const { wrapper, auth } = harness()
    const signal = vi.mocked(api.list).mock.calls[0]![2]!
    auth.applyUser({ ...auth.user!, permissions: [] }); await flushPromises()
    expect(signal.aborted).toBe(true); finish(result); await flushPromises()
    expect(wrapper.text()).toBe(''); wrapper.unmount()
  })
  it('切换租户中止凭证请求，卸载中止新列表请求', async () => {
    let finish!: (value: []) => void
    vi.mocked(api.credentials).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const { wrapper } = harness(); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '管理机器凭证')!.trigger('click')
    const signal = vi.mocked(api.credentials).mock.calls[0]![1]!
    useTenantStore().currentId = 'other-tenant'; await flushPromises()
    expect(signal.aborted).toBe(true); finish([]); await flushPromises()
    expect(wrapper.find('h3').exists()).toBe(false)
    const listSignal = vi.mocked(api.list).mock.calls.at(-1)![2]!
    wrapper.unmount(); expect(listSignal.aborted).toBe(true)
  })
  it('会话切换后不显示旧身份响应', async () => {
    let finish!: (value: typeof result) => void
    vi.mocked(api.list).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const { wrapper } = harness(); localStorage.setItem('token', 'different-session')
    finish(result); await flushPromises(); expect(wrapper.text()).not.toContain('ERP identity'); wrapper.unmount()
  })
})
