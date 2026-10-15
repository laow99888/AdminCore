import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import authApi, { type PersonalProfile } from '../src/api/auth'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import ProfileEditor from '../src/components/auth/ProfileEditor.vue'

vi.mock('../src/api/auth', () => ({ default: { profile: vi.fn(), saveProfile: vi.fn(), avatar: vi.fn(), uploadAvatar: vi.fn(), removeAvatar: vi.fn() } }))
vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
const stubs = {
  PrivateAvatar: true, EmailVerification: true,
  'el-button': defineComponent({ props: ['disabled', 'loading', 'nativeType'], template: '<button :type="nativeType || \'button\'" :disabled="disabled || loading"><slot /></button>' }),
  'el-input': defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' }),
  'el-form': defineComponent({ setup(_, { expose }) { expose({ validate: () => Promise.resolve(true), clearValidate: vi.fn() }) }, template: '<form><slot /></form>' }),
  'el-form-item': defineComponent({ template: '<div><slot /></div>' }),
  'el-alert': defineComponent({ props: ['title'], template: '<p role="alert">{{ title }}</p>' }),
}
const initial: PersonalProfile = { id: 'actor', username: 'actor', email: 'old@example.test', avatar: '', permissions: [], is_staff: false,
  first_name: 'original', last_name: 'family', phone: '+86 12345678', bio: 'original biography', profile_version: 1, has_avatar: false, avatar_enabled: false }
const latest = { ...initial, first_name: 'server latest', last_name: 'new family', email: 'latest@example.test', phone: '+86 87654321', bio: '<img src=x onerror=alert(1)>', profile_version: 2 }
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find(value => value.text() === text)!
async function setup() {
  const pinia = createPinia(), auth = useAuthStore(pinia), modules = useModuleStore(pinia)
  auth.token = 'isolated-profile-unit'; auth.applyUser({ ...initial })
  modules.config = { contract_version: 1, preset: 'minimal', modules: [] }
  const router = createRouter({ history: createMemoryHistory(), routes: ['/settings', '/login'].map(path => ({ path, component: { template: '<div />' } })) })
  await router.push('/settings'); await router.isReady()
  vi.mocked(authApi.profile).mockResolvedValueOnce({ ...initial }).mockResolvedValue({ ...latest })
  vi.mocked(authApi.saveProfile).mockRejectedValueOnce({ response: { status: 409 } }).mockResolvedValue({ ...latest, first_name: 'reviewed', profile_version: 3 })
  const wrapper = mount(ProfileEditor, { global: { plugins: [pinia, router], stubs } })
  await flushPromises()
  const input = () => wrapper.get<HTMLInputElement>('input[aria-label="名字"]')
  await input().setValue('retained draft'); await wrapper.get('form').trigger('submit'); await flushPromises()
  return { wrapper, auth, modules, input, router }
}
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); sessionStorage.clear() })

describe('个人资料白名单冲突比较', () => {
  it('409和比较都保留原版本与草稿，仅显式载入后携新版本保存', async () => {
    const { wrapper, input } = await setup()
    expect(authApi.profile).toHaveBeenCalledTimes(1); expect(input().element.value).toBe('retained draft')
    expect(button(wrapper, '保存资料').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit'); await flushPromises(); expect(authApi.saveProfile).toHaveBeenCalledTimes(1)
    await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
    expect(input().element.value).toBe('retained draft'); expect(wrapper.get('table').text()).toContain('server latest')
    expect(wrapper.findAll('tbody tr')).toHaveLength(5); expect(authApi.saveProfile).toHaveBeenCalledTimes(1)
    for (const label of ['姓氏', '名字', '邮箱', '电话', '个人简介']) expect(wrapper.get('table').text()).toContain(label)
    expect(wrapper.find('img').exists()).toBe(false); expect(wrapper.get('table').text()).toContain('<img src=x onerror=alert(1)>')
    await button(wrapper, '载入服务器最新值（替换当前输入）').trigger('click')
    expect(input().element.value).toBe('server latest'); expect(wrapper.find('table').exists()).toBe(false)
    await input().setValue('reviewed'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(authApi.saveProfile).toHaveBeenNthCalledWith(1, { first_name: 'retained draft', last_name: initial.last_name, email: initial.email, phone: initial.phone, bio: initial.bio, profile_version: 1 })
    expect(authApi.saveProfile).toHaveBeenNthCalledWith(2, { first_name: 'reviewed', last_name: latest.last_name, email: latest.email, phone: latest.phone, bio: latest.bio, profile_version: 2 })
  })
  it('比较只投影可编辑字段，不展示或应用额外安全字段、头像和权限', async () => {
    const { wrapper, auth } = await setup()
    vi.mocked(authApi.profile).mockResolvedValueOnce({ ...latest, permissions: ['*'], is_staff: true, avatar: 'https://private.example/secret-avatar', access_token: 'private-access-value', password: 'private-password-value', totp_secret: 'private-totp-value' } as any)
    await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
    for (const forbidden of ['private-access-value', 'private-password-value', 'private-totp-value', 'secret-avatar', 'permissions', 'is_staff']) expect(wrapper.get('table').text()).not.toContain(forbidden)
    await button(wrapper, '载入服务器最新值（替换当前输入）').trigger('click')
    expect(auth.user?.permissions).toEqual([]); expect(auth.user?.is_staff).toBe(false); expect(authApi.avatar).not.toHaveBeenCalled()
    expect(authApi.uploadAvatar).not.toHaveBeenCalled(); expect(authApi.removeAvatar).not.toHaveBeenCalled()
  })
  it('比较读取失败或返回其他账号/无效版本时保留草稿并允许重试', async () => {
    const { wrapper, input } = await setup()
    for (const value of [new Error('403'), { ...latest, id: 'other' }, { ...latest, profile_version: 0 }]) {
      if (value instanceof Error) vi.mocked(authApi.profile).mockRejectedValueOnce(value)
      else vi.mocked(authApi.profile).mockResolvedValueOnce(value)
      await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
      expect(wrapper.text()).toContain('最新值加载失败或已无权限'); expect(input().element.value).toBe('retained draft'); expect(wrapper.find('table').exists()).toBe(false)
    }
    await button(wrapper, '查看服务器最新值').trigger('click'); await flushPromises()
    expect(wrapper.get('table').text()).toContain('server latest'); expect(input().element.value).toBe('retained draft')
  })
  it.each(['logout', 'identity', 'forced-password', 'permission', 'module', 'token', 'unmount'])('%s 变化取消快照，迟到响应不能展示或回填', async action => {
    const { wrapper, auth, modules } = await setup()
    let complete!: (value: PersonalProfile) => void
    vi.mocked(authApi.profile).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    await button(wrapper, '查看服务器最新值').trigger('click')
    const signal = vi.mocked(authApi.profile).mock.calls.at(-1)![0]!
    if (action === 'logout') auth.clearSession()
    if (action === 'identity') auth.applyUser({ ...auth.user!, id: 'different' })
    if (action === 'forced-password') auth.applyUser({ ...auth.user!, must_change_password: true })
    if (action === 'permission') auth.applyUser({ ...auth.user!, permissions: ['changed'] })
    if (action === 'module') modules.config = { contract_version: 1, preset: 'standard', modules: [] }
    if (action === 'token') auth.token = 'replacement'
    if (action === 'unmount') wrapper.unmount()
    expect(signal.aborted).toBe(true)
    complete({ ...latest, bio: 'late private field', profile_version: 99 }); await flushPromises()
    expect(wrapper.text()).not.toContain('late private field'); expect(wrapper.find('table').exists()).toBe(false)
    expect(authApi.saveProfile).toHaveBeenCalledTimes(1)
    if (['logout', 'identity', 'forced-password'].includes(action)) expect(wrapper.find('form').exists()).toBe(false)
  })
})
