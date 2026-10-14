import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent } from 'vue'
vi.mock('../src/api', () => ({ usersApi: { sensitive: vi.fn() } }))
vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string) => text }))
vi.mock('../src/components', () => ({ BaseDialog: defineComponent({ template: '<div><slot /></div>' }) }))
import { usersApi } from '../src/api'
import UserSensitiveDialog from '../src/components/auth/UserSensitiveDialog.vue'
import { useAuthStore } from '../src/stores/auth'
const jwt = (sid: string, sequence = 1) => `fixture.${btoa(JSON.stringify({ sid, user_id: 'admin', session_version: 1, sequence }))}.fixture`
const raw = { email: 'original@example.test', phone: '13812341234' }
const PasswordStub = defineComponent({ props: ['execute', 'modelValue'], template: '<div />' })
async function harness() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/users', component: { template: '<div />' } }, { path: '/settings', component: { template: '<div />' } }] })
  await router.push('/users'); await router.isReady()
  const auth = useAuthStore(); auth.applyUser({ id: 'admin', username: 'admin', email: '', avatar: '', permissions: ['user:read', 'user:sensitive_read'] })
  const wrapper = mount(UserSensitiveDialog, { props: { target: { id: 'member', username: 'member' } }, global: { plugins: [router], stubs: { PasswordConfirmationDialog: PasswordStub } } })
  const reveal = wrapper.findComponent(PasswordStub).props('execute') as (password: string) => Promise<void>
  return { wrapper, auth, router, reveal }
}
describe('临时原值生命周期与会话归属', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); localStorage.setItem('token', jwt('old')); setActivePinia(createPinia()); vi.mocked(usersApi.sensitive).mockResolvedValue(raw) })
  afterEach(() => vi.useRealTimers())
  it('原值60秒自动销毁，手动关闭后不保留在DOM或storage', async () => {
    vi.useFakeTimers(); const { wrapper, reveal } = await harness(); await reveal('fixture'); await flushPromises()
    expect(wrapper.text()).toContain(raw.email); expect(wrapper.text()).toContain(raw.phone)
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(raw.email)
    await vi.advanceTimersByTimeAsync(60_000); expect(wrapper.text()).not.toContain(raw.email); expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })
  it('权限撤回同步清原值；同sid轮换保留，跨tab切换清除', async () => {
    const { wrapper, reveal, auth } = await harness(); await reveal('fixture'); await flushPromises()
    const old = localStorage.getItem('token')!; localStorage.setItem('token', jwt('old', 2)); window.dispatchEvent(new StorageEvent('storage', { key: 'token', oldValue: old, newValue: jwt('old', 2) }))
    await flushPromises(); expect(wrapper.text()).toContain(raw.email)
    auth.applyUser({ ...auth.user!, permissions: ['user:read'] }); await flushPromises()
    expect(wrapper.text()).not.toContain(raw.email); wrapper.unmount()
    const next = await harness(); await next.reveal('fixture'); await flushPromises()
    localStorage.setItem('token', jwt('replacement')); window.dispatchEvent(new StorageEvent('storage', { key: 'token', oldValue: jwt('old'), newValue: jwt('replacement') }))
    await flushPromises(); expect(next.wrapper.text()).not.toContain(raw.email); next.wrapper.unmount()
  })
  it('卸载abort请求，即使不响应abort的适配器迟到成功也不展示', async () => {
    let finish!: (value: typeof raw) => void
    vi.mocked(usersApi.sensitive).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const { wrapper, reveal } = await harness(); const pending = reveal('fixture')
    const signal = vi.mocked(usersApi.sensitive).mock.calls[0]![2]!
    wrapper.unmount(); expect(signal.aborted).toBe(true); finish(raw); await pending
    expect(wrapper.emitted('close')).toBeUndefined()
  })
  it('迟到权限撤回与storage清空不恢复原值，失败仍reject给密码确认重试', async () => {
    let finish!: (value: typeof raw) => void
    vi.mocked(usersApi.sensitive).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const { wrapper, reveal, auth } = await harness(); const pending = reveal('fixture')
    auth.applyUser({ ...auth.user!, permissions: [] }); finish(raw); await pending; await flushPromises()
    expect(wrapper.text()).not.toContain(raw.email); wrapper.unmount()
    const next = await harness(); vi.mocked(usersApi.sensitive).mockRejectedValueOnce(new Error('forbidden'))
    await expect(next.reveal('fixture')).rejects.toThrow('forbidden'); expect(next.wrapper.text()).not.toContain(raw.email)
    next.wrapper.unmount()
  })
})
