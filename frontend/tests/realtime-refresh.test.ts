import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, shallowMount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppHeader from '../src/components/layout/AppHeader.vue'
import { useRealtimeUpdates } from '../src/composables/useRealtimeUpdates'
import { useLatestRead } from '../src/composables/useLatestRead'
import { useEditConflict } from '../src/composables/useEditConflict'
import { startRealtimeClient } from '../src/utils/realtime'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'
import { i18n } from '../src/i18n'

vi.mock('../src/api', () => ({ notificationsApi: { unreadCount: vi.fn().mockResolvedValue(1) } }))
vi.mock('../src/utils/realtime', async original => ({ ...await original<typeof import('../src/utils/realtime')>(), startRealtimeClient: vi.fn(() => vi.fn()) }))

const jwt = (sid: string, generation: number, version = 1) => `fixture.${btoa(JSON.stringify({ sid, user_id: 'member', session_version: version, generation }))}.fixture`

function setup() {
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useAuthStore(), modules = useModuleStore()
  auth.token = 'realtime-refresh-fixture'
  auth.user = { id: 'member', username: 'member', email: '', avatar: '', permissions: ['task:read'] }
  modules.config = { contract_version: 1, preset: 'standard', modules: ['tasks', 'notifications', 'realtime'].map(key => ({ key, title: key, enabled: true, dependencies: [], paths: [] })) }
  return { pinia, auth, modules }
}
async function header(access?: string, organization = false) {
  const state = setup()
  const tenantLoad = vi.spyOn(useTenantStore(), 'load').mockResolvedValue(undefined)
  if (organization) state.modules.config!.modules.push({ key: 'organization', title: '组织', enabled: true, dependencies: [], paths: ['/organization'] })
  if (access) state.auth.token = access
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { render: () => null } }] })
  await router.push('/'); await router.isReady()
  const wrapper = shallowMount(AppHeader, { global: { plugins: [state.pinia, i18n, router] } })
  await flushPromises()
  return { ...state, wrapper, tenantLoad }
}

describe('权限刷新保留实时退避与已加载列表', () => {
  beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it.each([false, true])('组织模块启用为 %s 时按能力加载租户，不依赖测试环境特判', async organization => {
    const { wrapper, tenantLoad } = await header(undefined, organization)
    expect(tenantLoad).toHaveBeenCalledTimes(organization ? 1 : 0)
    wrapper.unmount(); expect(vi.getTimerCount()).toBe(0)
  })

  it('同设备access轮换保留流，安全会话替换才终止并重建', async () => {
    const jwt = (sid: string, generation: number) => `fixture.${btoa(JSON.stringify({ sid, user_id: 'member', session_version: 1, generation }))}.fixture`
    const { auth, wrapper } = await header(jwt('device', 1))
    const stop = vi.mocked(startRealtimeClient).mock.results[0]!.value
    auth.token = jwt('device', 2); await nextTick()
    expect(startRealtimeClient).toHaveBeenCalledOnce(); expect(stop).not.toHaveBeenCalled()
    auth.token = jwt('replacement', 1); await nextTick()
    expect(startRealtimeClient).toHaveBeenCalledTimes(2); expect(stop).toHaveBeenCalledOnce()
    wrapper.unmount(); expect(vi.getTimerCount()).toBe(0)
  })

  it('相同身份/权限/模块的新对象不会重建连接或打断退避，真正撤权仍终止', async () => {
    const { auth, modules, wrapper } = await header()
    expect(startRealtimeClient).toHaveBeenCalledOnce()
    const stop = vi.mocked(startRealtimeClient).mock.results[0]!.value
    auth.user = { ...auth.user!, permissions: [...auth.user!.permissions!] }
    modules.config = JSON.parse(JSON.stringify(modules.config))
    await nextTick()
    expect(startRealtimeClient).toHaveBeenCalledOnce(); expect(stop).not.toHaveBeenCalled()
    modules.config!.modules.find(item => item.key === 'realtime')!.enabled = false
    await nextTick()
    expect(stop).toHaveBeenCalledOnce(); expect(startRealtimeClient).toHaveBeenCalledOnce()
    wrapper.unmount(); expect(vi.getTimerCount()).toBe(0)
  })

  it('权限或设备凭据实际改变会停止旧连接并以新上下文重新建立', async () => {
    const { auth, wrapper } = await header()
    const stop = vi.mocked(startRealtimeClient).mock.results[0]!.value
    auth.user!.permissions = ['task:read', 'user:read']; await nextTick()
    expect(stop).toHaveBeenCalledOnce(); expect(startRealtimeClient).toHaveBeenCalledTimes(2)
    const replacement = vi.mocked(startRealtimeClient).mock.results[1]!.value
    auth.token = 'replaced-device'; await nextTick()
    expect(replacement).toHaveBeenCalledOnce(); expect(startRealtimeClient).toHaveBeenCalledTimes(3)
    wrapper.unmount(); expect(vi.getTimerCount()).toBe(0)
  })

  it('列表相同权限刷新保留内容和请求代次，撤权清空并使进行中响应失效', async () => {
    const { pinia, auth } = setup()
    const refresh = vi.fn().mockResolvedValue(undefined), clear = vi.fn()
    let guard!: () => () => boolean
    const harness = defineComponent({ setup() { guard = useRealtimeUpdates('tasks', refresh, clear); return () => h('div') } })
    const wrapper = mount(harness, { global: { plugins: [pinia] } })
    const current = guard()
    auth.user = { ...auth.user!, permissions: [...auth.user!.permissions!] }; await nextTick()
    expect(clear).not.toHaveBeenCalled(); expect(refresh).not.toHaveBeenCalled(); expect(current()).toBe(true)
    auth.user!.permissions = []; await nextTick()
    expect(clear).toHaveBeenCalledOnce(); expect(refresh).not.toHaveBeenCalled(); expect(current()).toBe(false)
    wrapper.unmount(); expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['session', 'version', 'permission'])('正常access刷新保留列表、历史读取和冲突草稿，%s 变化仍清理并失效', async change => {
    const { pinia, auth } = setup()
    auth.token = jwt('device', 1)
    const refresh = vi.fn().mockResolvedValue(undefined), clearList = vi.fn(), clearRead = vi.fn()
    let list!: ReturnType<typeof useRealtimeUpdates>, read!: ReturnType<typeof useLatestRead>
    let conflict!: ReturnType<typeof useEditConflict<{ version: number }>>
    let finish!: (value: { version: number }) => void
    const fetch = vi.fn<(_: string, signal: AbortSignal) => Promise<{ version: number }>>().mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(defineComponent({ setup() {
      list = useRealtimeUpdates('tasks', refresh, clearList)
      read = useLatestRead(clearRead)
      conflict = useEditConflict({ identifier: () => 'row', current: () => true, fetch, apply: vi.fn() })
      return () => h('div')
    } }), { global: { plugins: [pinia] } })
    const currentList = list(), currentRead = read()
    conflict.mark(); const pending = conflict.inspect()
    const signal = fetch.mock.calls[0]![1]
    auth.token = jwt('device', 2); await nextTick()
    expect(clearList).not.toHaveBeenCalled(); expect(clearRead).not.toHaveBeenCalled()
    expect(currentList()).toBe(true); expect(currentRead()).toBe(true)
    expect(conflict.active.value).toBe(true); expect(signal.aborted).toBe(false)
    finish({ version: 2 }); await pending
    expect(conflict.latest.value).toEqual({ version: 2 })
    if (change === 'session') auth.token = jwt('replacement', 1)
    if (change === 'version') auth.token = jwt('device', 3, 2)
    if (change === 'permission') auth.user!.permissions = []
    await nextTick()
    expect(clearList).toHaveBeenCalledOnce(); expect(clearRead).toHaveBeenCalledOnce()
    expect(currentList()).toBe(false); expect(currentRead()).toBe(false)
    expect(conflict.active.value).toBe(false); expect(conflict.latest.value).toBeUndefined()
    wrapper.unmount(); expect(vi.getTimerCount()).toBe(0)
  })
})
