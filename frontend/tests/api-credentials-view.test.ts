import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
vi.mock('../src/api/apiCredentials', () => ({ apiCredentialsApi: { list: vi.fn(), scopes: vi.fn(), create: vi.fn(), revoke: vi.fn(), rotate: vi.fn(), statistics: vi.fn() } }))
vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string) => text, registerUiMessages: vi.fn() }))
vi.mock('../src/components/layout/AppLayout.vue', () => ({ default: defineComponent({ template: '<main><slot /></main>' }) }))
vi.mock('../src/components/auth/PasswordConfirmationDialog.vue', () => ({ default: defineComponent({ name: 'ConfirmStub', props: ['execute', 'modelValue', 'disabled'], emits: ['update:modelValue', 'busy'], template: '<div />' }) }))
vi.mock('../src/components', () => ({
  BaseButton: defineComponent({ props: ['disabled', 'nativeType'], template: '<button :disabled="disabled" :type="nativeType || \'button\'"><slot /></button>' }),
  BaseTable: defineComponent({ props: ['data'], template: '<div><div v-for="row in data" :key="row.id">{{ row.name }}<slot name="actions" :row="row" /></div></div>' }),
}))
import { apiCredentialsApi } from '../src/api/apiCredentials'
import APICredentialsView from '../src/views/settings/APICredentialsView.vue'
import { useAuthStore } from '../src/stores/auth'

const InputStub = defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' })
const CheckboxGroup = defineComponent({ name: 'ChoiceStub', props: ['modelValue'], emits: ['update:modelValue'], template: '<div><slot /></div>' })
const credential = { id: 'fixture', name: 'fixture', scopes: ['task:read'], created_at: '', expires_at: '2099-10-20T00:00:00Z', revoked_at: null, last_used_at: null, version: 1, rotated_at: null, accepted_requests: 0, statistics_started_at: '2026-10-18T00:00:00Z' }
async function harness() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/integrations/credentials', component: { template: '<div />' } }, { path: '/other', component: { template: '<div />' } }] })
  await router.push('/integrations/credentials'); await router.isReady()
  const auth = useAuthStore()
  auth.applyUser({ id: 'owner', username: 'owner', email: '', avatar: '', permissions: ['api_credential:read', 'api_credential:create', 'api_credential:revoke'] })
  const wrapper = mount(APICredentialsView, { global: { plugins: [router], stubs: {
    'el-alert': defineComponent({ props: ['title'], template: '<p>{{ title }}</p>' }),
    'el-card': defineComponent({ template: '<div><slot /></div>' }),
    'el-form': defineComponent({ template: '<form><slot /></form>' }),
    'el-form-item': defineComponent({ template: '<div><slot /></div>' }),
    'el-input': InputStub, 'el-input-number': InputStub, 'el-checkbox-group': CheckboxGroup, 'el-checkbox': true,
    'el-dialog': defineComponent({ name: 'SecretStub', props: ['modelValue'], emits: ['update:modelValue', 'closed'], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' }),
  } } })
  await flushPromises()
  async function prepare() {
    await wrapper.findAll('input')[0]!.setValue('fixture name')
    wrapper.findComponent(CheckboxGroup).vm.$emit('update:modelValue', ['task:read']); await flushPromises()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    return wrapper.findComponent({ name: 'ConfirmStub' })
  }
  return { wrapper, auth, router, prepare }
}

describe('开放凭证页面的密钥生命周期', () => {
  beforeEach(() => {
    vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear(); localStorage.setItem('token', 'fixture-session'); setActivePinia(createPinia())
    vi.mocked(apiCredentialsApi.list).mockResolvedValue({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 0 } })
    vi.mocked(apiCredentialsApi.scopes).mockResolvedValue([{ code: 'task:read', label: '读取任务摘要' }])
    vi.mocked(apiCredentialsApi.create).mockResolvedValue({ ...credential, token: 'one-time-fixture-secret' })
  })
  it('确认后只在临时对话框展示密钥；关闭即清空且不写浏览器存储', async () => {
    const { wrapper, prepare } = await harness()
    const confirm = await prepare()
    expect(confirm.props('modelValue')).toBe(true)
    await confirm.props('execute')('fixture-password'); await flushPromises()
    expect(wrapper.get('textarea').element.value).toBe('one-time-fixture-secret')
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain('one-time-fixture-secret')
    wrapper.findAllComponents({ name: 'SecretStub' }).find(dialog => dialog.props('modelValue') === true)!.vm.$emit('update:modelValue', false); await flushPromises()
    expect(wrapper.find('textarea').exists()).toBe(false)
    wrapper.unmount()
  })
  it('切换登录会话后丢弃迟到签发结果，权限撤销清空密钥', async () => {
    let finish!: (value: Awaited<ReturnType<typeof apiCredentialsApi.create>>) => void
    vi.mocked(apiCredentialsApi.create).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const { wrapper, prepare, auth } = await harness()
    const confirm = await prepare(), pending = confirm.props('execute')('fixture-password')
    localStorage.setItem('token', 'different-session')
    finish({ ...credential, token: 'late-secret' })
    await pending; await flushPromises()
    expect(wrapper.find('textarea').exists()).toBe(false)
    auth.applyUser({ ...auth.user!, permissions: ['api_credential:read'] }); await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    wrapper.unmount()
  })
  it('加载错误可刷新，卸载中止本次加载请求', async () => {
    vi.mocked(apiCredentialsApi.list).mockRejectedValueOnce(new Error('unavailable'))
    const { wrapper } = await harness()
    expect(wrapper.text()).toContain('开放凭证加载失败')
    await wrapper.findAll('button')[0]!.trigger('click'); await flushPromises()
    const signal = vi.mocked(apiCredentialsApi.list).mock.calls.at(-1)![2]!
    wrapper.unmount(); expect(signal.aborted).toBe(true)
  })
  it('轮换使用当前版本并仅展示新密钥，撤销权限丢失立即清除', async () => {
    vi.mocked(apiCredentialsApi.list).mockResolvedValue({ items: [credential], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } })
    vi.mocked(apiCredentialsApi.rotate).mockResolvedValue({ ...credential, version: 2, token: 'rotated-only-secret' })
    const { wrapper, auth } = await harness()
    await wrapper.findAll('button').find(button => button.text() === '轮换密钥')!.trigger('click')
    await wrapper.findComponent({ name: 'ConfirmStub' }).props('execute')('confirmed-password')
    await flushPromises()
    expect(apiCredentialsApi.rotate).toHaveBeenCalledWith('fixture', 1, 'confirmed-password')
    expect(wrapper.get('textarea').element.value).toBe('rotated-only-secret')
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain('rotated-only-secret')
    auth.applyUser({ ...auth.user!, permissions: ['api_credential:read', 'api_credential:create'] })
    await flushPromises()
    expect(wrapper.find('textarea').exists()).toBe(false)
    wrapper.unmount()
  })
  it('轮换冲突不显示密钥或自动重试；切换会话丢弃迟到密钥', async () => {
    vi.mocked(apiCredentialsApi.list).mockResolvedValue({ items: [credential], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } })
    vi.mocked(apiCredentialsApi.rotate).mockRejectedValueOnce(new Error('version conflict'))
    const { wrapper } = await harness()
    await wrapper.findAll('button').find(button => button.text() === '轮换密钥')!.trigger('click')
    const execute = wrapper.findComponent({ name: 'ConfirmStub' }).props('execute')
    await expect(execute('confirmed-password')).rejects.toThrow('version conflict')
    expect(apiCredentialsApi.rotate).toHaveBeenCalledTimes(1)
    expect(wrapper.find('textarea').exists()).toBe(false)
    let finish!: (value: Awaited<ReturnType<typeof apiCredentialsApi.rotate>>) => void
    vi.mocked(apiCredentialsApi.rotate).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const pending = execute('confirmed-password')
    localStorage.setItem('token', 'another-session')
    finish({ ...credential, version: 2, token: 'late-rotated-secret' })
    await pending; await flushPromises()
    expect(wrapper.find('textarea').exists()).toBe(false)
    wrapper.unmount()
  })
})
