import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { ipPolicyApi } from '../src/api/ipPolicy'
import IPPolicyView from '../src/views/system/IPPolicyView.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api/ipPolicy', () => ({ ipPolicyApi: { detail: vi.fn(), preview: vi.fn(), save: vi.fn() } }))
vi.mock('../src/components', () => ({
  AppLayout: defineComponent({ template: '<main><slot /></main>' }),
  BaseCard: defineComponent({ template: '<section><slot name="header" /><slot /></section>' }),
  BaseButton: defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }),
}))
const stubs = {
  'el-button': defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }),
  'el-input': defineComponent({ props: ['modelValue', 'disabled'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />' }),
  'el-form': defineComponent({ template: '<form><slot /></form>' }),
  'el-form-item': defineComponent({ template: '<div><slot /></div>' }),
  'el-switch': true,
}
const policy = { enabled: false, allow: ['127.0.0.1/32'], deny: [], version: 1, updated_at: '' }
let mounted: VueWrapper | undefined
const button = (wrapper: VueWrapper, value: string) => wrapper.findAll('button').find(item => item.text() === value)!
async function setup(permissions = ['*']) {
  const pinia = createPinia(), auth = useAuthStore(pinia), modules = useModuleStore(pinia)
  auth.token = 'unit-policy-fixture'; auth.applyUser({ id: 'actor', username: 'actor', email: '', avatar: '', is_staff: false, permissions })
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'ip_policy', title: 'IP', enabled: true, paths: ['/system/ip-policy'], dependencies: [] }] }
  const router = createRouter({ history: createMemoryHistory(), routes: ['/system/ip-policy', '/login'].map(path => ({ path, component: { template: '<div />' } })) })
  await router.push('/system/ip-policy'); await router.isReady()
  vi.mocked(ipPolicyApi.detail).mockResolvedValue({ ...policy })
  vi.mocked(ipPolicyApi.preview).mockResolvedValue({ source_ip: '127.0.0.1', allowed: true })
  vi.mocked(ipPolicyApi.save).mockResolvedValue({ ...policy, version: 2 })
  mounted = mount(IPPolicyView, { global: { plugins: [pinia, router], stubs } }); await flushPromises()
  return { wrapper: mounted, auth, modules }
}
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); sessionStorage.clear() })
afterEach(() => { mounted?.unmount(); mounted = undefined })

it('当前来源预检通过才允许保存，网络变更使预检失效，密码仅发送一次', async () => {
  const { wrapper } = await setup()
  const password = () => wrapper.get<HTMLTextAreaElement>('textarea[aria-label="当前密码"]')
  await password().setValue('unit-confirmation')
  expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
  await button(wrapper, '预检当前来源').trigger('click'); await flushPromises()
  expect(ipPolicyApi.preview).toHaveBeenCalledWith({ enabled: false, allow: ['127.0.0.1/32'], deny: [] }, expect.any(AbortSignal))
  expect(button(wrapper, '保存').attributes('disabled')).toBeUndefined()
  await wrapper.get('textarea[aria-label="允许网络"]').setValue('127.0.0.1\n::1')
  expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
  await button(wrapper, '预检当前来源').trigger('click'); await flushPromises()
  await button(wrapper, '保存').trigger('click'); await flushPromises()
  expect(ipPolicyApi.save).toHaveBeenCalledTimes(1)
  expect(ipPolicyApi.save).toHaveBeenCalledWith({ enabled: false, allow: ['127.0.0.1', '::1'], deny: [], version: 1, current_password: 'unit-confirmation' })
  expect(password().element.value).toBe('')
  expect(localStorage.getItem('unit-confirmation')).toBeNull()
})
it('失败不保留密码；版本冲突只在显式应用后替换输入', async () => {
  const { wrapper } = await setup()
  await wrapper.get('textarea[aria-label="允许网络"]').setValue('127.0.0.1')
  await button(wrapper, '预检当前来源').trigger('click'); await flushPromises()
  vi.mocked(ipPolicyApi.save).mockRejectedValueOnce({ response: { status: 409 } })
  await wrapper.get('textarea[aria-label="当前密码"]').setValue('fixture')
  await button(wrapper, '保存').trigger('click'); await flushPromises()
  expect(wrapper.get<HTMLTextAreaElement>('textarea[aria-label="当前密码"]').element.value).toBe('')
  vi.mocked(ipPolicyApi.detail).mockResolvedValue({ ...policy, allow: ['::1/128'], version: 2 })
  await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
  expect(wrapper.get<HTMLTextAreaElement>('textarea[aria-label="允许网络"]').element.value).toBe('127.0.0.1')
  await button(wrapper, '载入服务器最新值（替换当前输入）').trigger('click'); await flushPromises()
  expect(wrapper.get<HTMLTextAreaElement>('textarea[aria-label="允许网络"]').element.value).toBe('::1/128')
  expect(button(wrapper, '保存').attributes('disabled')).toBeDefined()
})
it('只读人员能预检但不能修改或发送密码', async () => {
  const { wrapper } = await setup(['ip_policy:read'])
  expect(wrapper.find('textarea[aria-label="当前密码"]').exists()).toBe(false)
  expect(wrapper.get('textarea[aria-label="允许网络"]').attributes('disabled')).toBeDefined()
  await button(wrapper, '预检当前来源').trigger('click'); await flushPromises()
  expect(ipPolicyApi.preview).toHaveBeenCalledOnce(); expect(ipPolicyApi.save).not.toHaveBeenCalled()
})
it.each(['permission', 'module', 'identity', 'unmount'])('%s 变化中止读取，不接受旧身份的迟到结果', async action => {
  const { wrapper, auth, modules } = await setup()
  let complete!: (value: { source_ip: string; allowed: boolean }) => void
  vi.mocked(ipPolicyApi.preview).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  await button(wrapper, '预检当前来源').trigger('click')
  const signal = vi.mocked(ipPolicyApi.preview).mock.calls[0]![1]!
  if (action === 'permission') auth.applyUser({ ...auth.user!, permissions: [] })
  if (action === 'module') modules.config!.modules[0]!.enabled = false
  if (action === 'identity') auth.applyUser({ ...auth.user!, id: 'other' })
  if (action === 'unmount') { wrapper.unmount(); mounted = undefined }
  await flushPromises(); expect(signal.aborted).toBe(true)
  complete({ source_ip: 'old-private-source', allowed: true }); await flushPromises()
  expect(wrapper.text()).not.toContain('old-private-source'); expect(ipPolicyApi.save).not.toHaveBeenCalled()
})
