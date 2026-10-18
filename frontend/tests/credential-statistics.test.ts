import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
vi.mock('../src/api/apiCredentials', () => ({ apiCredentialsApi: { statistics: vi.fn() } }))
vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string) => text, registerUiMessages: vi.fn() }))
vi.mock('../src/components', () => ({ BaseButton: defineComponent({ template: '<button><slot /></button>' }) }))
import { apiCredentialsApi, type APICredential, type CredentialStatistics } from '../src/api/apiCredentials'
import CredentialStatisticsDialog from '../src/components/integrations/CredentialStatisticsDialog.vue'
import { useAuthStore } from '../src/stores/auth'

const credential: APICredential = { id: 'fixture', name: 'fixture', scopes: ['task:read'], created_at: '', expires_at: '', revoked_at: null, last_used_at: null, version: 1, rotated_at: null, accepted_requests: 0, statistics_started_at: '2026-10-18T00:00:00Z' }
const statistics: CredentialStatistics = { days: 7, timezone: 'UTC', statistics_started_at: credential.statistics_started_at, accepted_requests: 15, recent_requests: 4, daily: [{ day: '2026-10-18', requests: 4 }] }
function harness() {
  const auth = useAuthStore()
  auth.applyUser({ id: 'owner', username: 'owner', email: '', avatar: '', permissions: ['api_credential:read'] })
  const wrapper = mount(CredentialStatisticsDialog, { props: { credential }, global: { stubs: {
    'el-dialog': defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>' }),
    'el-alert': defineComponent({ props: ['title'], template: '<p role="alert">{{ title }}</p>' }),
    'el-input-number': true,
  } } })
  return { wrapper, auth }
}
describe('凭证统计的权限与迟到响应', () => {
  beforeEach(() => {
    vi.clearAllMocks(); localStorage.clear(); localStorage.setItem('token', 'fixture-session'); setActivePinia(createPinia())
    vi.mocked(apiCredentialsApi.statistics).mockResolvedValue(statistics)
  })
  it('展示授权请求语义、UTC日统计和空状态', async () => {
    const { wrapper } = harness(); await flushPromises()
    expect(wrapper.text()).toContain('不代表操作成功')
    expect(wrapper.text()).toContain('累计已授权请求：15')
    expect(wrapper.text()).toContain('2026-10-18 UTC')
    vi.mocked(apiCredentialsApi.statistics).mockResolvedValue({ ...statistics, daily: [], recent_requests: 0 })
    await wrapper.findAll('button')[0]!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('所选期间暂无请求')
    wrapper.unmount()
  })
  it('错误可重试；换凭证中止旧请求，不接受迟到统计', async () => {
    vi.mocked(apiCredentialsApi.statistics).mockRejectedValueOnce(new Error('offline'))
    const { wrapper } = harness(); await flushPromises()
    expect(wrapper.text()).toContain('调用统计加载失败')
    let finish!: (value: CredentialStatistics) => void
    vi.mocked(apiCredentialsApi.statistics).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await wrapper.findAll('button')[0]!.trigger('click')
    const signal = vi.mocked(apiCredentialsApi.statistics).mock.calls.at(-1)![2]!
    await wrapper.setProps({ credential: { ...credential, id: 'other' } }); await flushPromises()
    expect(signal.aborted).toBe(true)
    finish({ ...statistics, accepted_requests: 999999 }); await flushPromises()
    expect(wrapper.text()).not.toContain('999999')
    wrapper.unmount()
  })
  it('权限丢失清空数据，关闭和卸载中止请求', async () => {
    const { wrapper, auth } = harness(); await flushPromises()
    const signal = vi.mocked(apiCredentialsApi.statistics).mock.calls[0]![2]!
    auth.applyUser({ ...auth.user!, permissions: [] }); await flushPromises()
    expect(signal.aborted).toBe(true)
    expect(wrapper.text()).not.toContain('累计已授权请求：15')
    await wrapper.setProps({ credential: null }); await flushPromises()
    expect(wrapper.text()).toBe('')
    wrapper.unmount()
  })
  it('会话切换后的迟到响应不得展示', async () => {
    let finish!: (value: CredentialStatistics) => void
    vi.mocked(apiCredentialsApi.statistics).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const { wrapper } = harness()
    localStorage.setItem('token', 'different-session')
    finish(statistics); await flushPromises()
    expect(wrapper.text()).not.toContain('累计已授权请求：15')
    wrapper.unmount()
  })
})
