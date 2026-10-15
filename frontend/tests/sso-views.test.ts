import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, reactive } from 'vue'
const auth = vi.hoisted(() => ({ loginSSO: vi.fn(), cancelPendingLogin: vi.fn(), can: vi.fn(), user: null as any }))
vi.mock('../src/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('../src/api/sso', () => ({ ssoApi: { config: vi.fn(), start: vi.fn(), status: vi.fn(), complete: vi.fn(), cancel: vi.fn(), list: vi.fn(), bind: vi.fn(), unbind: vi.fn() } }))
vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string) => text, registerUiMessages: vi.fn() }))
vi.mock('../src/components/layout/AppLayout.vue', () => ({ default: defineComponent({ template: '<main><slot /></main>' }) }))
vi.mock('../src/components/auth/PasswordConfirmationDialog.vue', () => ({ default: defineComponent({ name: 'ConfirmStub', props: ['execute', 'modelValue', 'disabled', 'confirmText'], template: '<div />' }) }))
vi.mock('../src/components', () => ({
  BaseButton: defineComponent({ props: ['disabled', 'nativeType'], template: '<button :disabled="disabled" :type="nativeType || \'button\'"><slot /></button>' }),
  BaseTable: defineComponent({ props: ['data'], template: '<div><div v-for="row in data" :key="row.id">{{ row.username }}<slot name="actions" :row="row" /></div></div>' }),
}))
import { ssoApi } from '../src/api/sso'
import EnterpriseLoginView from '../src/views/auth/EnterpriseLoginView.vue'
import ExternalIdentitiesView from '../src/views/settings/ExternalIdentitiesView.vue'
import SSOEntry from '../src/components/auth/SSOEntry.vue'
const stubs = {
  'el-button': defineComponent({ props: ['disabled', 'nativeType'], template: '<button :disabled="disabled" :type="nativeType || \'button\'"><slot /></button>' }),
  'el-input': defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' }),
  'el-form': defineComponent({ template: '<form><slot /></form>' }),
  'el-form-item': defineComponent({ template: '<label><slot /></label>' }),
  'el-alert': defineComponent({ props: ['title'], template: '<p role="alert">{{ title }}</p>' }),
  'el-card': defineComponent({ template: '<div><slot /></div>' }),
}
async function harness(component: any, path = '/enterprise-login?result=ready') {
  const router = createRouter({ history: createMemoryHistory(), routes: ['/enterprise-login', '/integrations/identities', '/login', '/'].map(path => ({ path, component: { template: '<div />' } })) })
  await router.push(path); await router.isReady()
  const wrapper = mount(component, { global: { plugins: [router], stubs } })
  await flushPromises()
  return { wrapper, router }
}
describe('企业登录和绑定页面', () => {
  beforeEach(() => {
    vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear()
    auth.user = reactive({ id: 'admin', is_staff: true }); auth.can.mockReturnValue(true)
    vi.mocked(ssoApi.config).mockResolvedValue({ enabled: true, label: 'Company SSO' })
    vi.mocked(ssoApi.status).mockResolvedValue({ ready: true, mfa_required: true, captcha: { required: false } })
    vi.mocked(ssoApi.cancel).mockResolvedValue()
    vi.mocked(ssoApi.list).mockResolvedValue({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 0 } })
  })
  it('不在完成安全校验前登录；失败清空动态码、支持重试与本地入口', async () => {
    auth.loginSSO.mockRejectedValueOnce({ response: { status: 401, data: { data: { code: 'mfa_invalid' } } } }).mockResolvedValueOnce({})
    const { wrapper, router } = await harness(EnterpriseLoginView)
    expect(auth.loginSSO).not.toHaveBeenCalled()
    await wrapper.get('input').setValue('123456'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('input').element.value).toBe('')
    expect(wrapper.text()).toContain('认证码无效')
    await wrapper.get('input').setValue('654321'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(auth.loginSSO).toHaveBeenLastCalledWith({ otp_code: '654321' }, expect.any(AbortSignal))
    expect(router.currentRoute.value.path).toBe('/')
    wrapper.unmount(); expect(auth.cancelPendingLogin).toHaveBeenCalled()
  })
  it('禁用/配置失败始终保留本地登录，卸载中止配置请求', async () => {
    vi.mocked(ssoApi.config).mockResolvedValue({ enabled: false })
    const { wrapper, router } = await harness(EnterpriseLoginView, '/enterprise-login')
    expect(wrapper.text()).toContain('企业登录未启用')
    await wrapper.findAll('button').find(item => item.text().includes('使用本地'))!.trigger('click'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/login')
    const signal = vi.mocked(ssoApi.config).mock.calls.at(-1)![0]!
    wrapper.unmount(); expect(signal.aborted).toBe(true)
  })
  it('SSO 入口默认关闭；配置请求 404 隐藏入口，网络失败可重试', async () => {
    vi.mocked(ssoApi.config).mockRejectedValueOnce({ response: { status: 404 } })
    const { wrapper } = await harness(SSOEntry, '/login')
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
    vi.mocked(ssoApi.config).mockRejectedValueOnce(new Error('network'))
    const retry = await harness(SSOEntry, '/login')
    expect(retry.wrapper.text()).toContain('本地登录仍可使用')
    await retry.wrapper.get('button').trigger('click'); await flushPromises()
    expect(retry.wrapper.text()).toContain('Company SSO'); retry.wrapper.unmount()
  })
  it('只有管理员和权限同时满足才展示绑定；有效 UUID + subject 后才可密码确认', async () => {
    const { wrapper } = await harness(ExternalIdentitiesView, '/integrations/identities')
    await wrapper.findAll('input')[0]!.setValue('10000000-0000-4000-8000-000000000001')
    await wrapper.findAll('input')[1]!.setValue('opaque-subject')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const confirmation = wrapper.findComponent({ name: 'ConfirmStub' })
    expect(confirmation.props('modelValue')).toBe(true)
    expect(confirmation.props('confirmText')).toBe('确认绑定')
    await confirmation.props('execute')('fixture-password')
    expect(ssoApi.bind).toHaveBeenCalledWith('10000000-0000-4000-8000-000000000001', 'opaque-subject', 'fixture-password')
    wrapper.unmount()
    auth.user = { id: 'member', is_staff: false }
    const member = await harness(ExternalIdentitiesView, '/integrations/identities')
    expect(member.wrapper.find('form').exists()).toBe(false); member.wrapper.unmount()
  })
})
