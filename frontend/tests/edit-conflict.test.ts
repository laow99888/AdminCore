import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, ref } from 'vue'
import { useEditConflict } from '../src/composables/useEditConflict'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import EditConflictPanel from '../src/components/common/EditConflictPanel.vue'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })
type Snapshot = { version: number; name: string }
function harness(fetch = vi.fn<(_: string, signal: AbortSignal) => Promise<Snapshot>>().mockResolvedValue({ version: 2, name: 'server' })) {
  const pinia = createPinia(), auth = useAuthStore(pinia), modules = useModuleStore(pinia)
  auth.token = 'fixture'; auth.applyUser({ id: 'actor', username: 'actor', email: '', avatar: '', permissions: ['edit'] })
  const id = ref('row'), current = ref(true), apply = vi.fn()
  let conflict!: ReturnType<typeof useEditConflict<Snapshot>>
  const wrapper = mount(defineComponent({ setup() { conflict = useEditConflict({ identifier: () => id.value, current: () => current.value, fetch, apply }); return () => h('div') } }), { global: { plugins: [pinia] } })
  return { conflict, wrapper, auth, modules, id, current, fetch, apply }
}

describe('版本冲突快照生命周期', () => {
  it('标记冲突不写草稿，查看也不自动应用，只有显式载入才应用', async () => {
    const { conflict, apply, wrapper } = harness()
    conflict.mark(); expect(conflict.active.value).toBe(true); expect(apply).not.toHaveBeenCalled()
    await conflict.inspect(); expect(conflict.latest.value?.version).toBe(2); expect(apply).not.toHaveBeenCalled()
    conflict.applyLatest(); expect(apply).toHaveBeenCalledExactlyOnceWith({ version: 2, name: 'server' })
    expect(conflict.active.value).toBe(false); expect(conflict.latest.value).toBeUndefined(); wrapper.unmount()
  })
  it('加载失败不换版本，显式重试恢复；无当前权限时不能载入', async () => {
    const fetch = vi.fn<(_: string, signal: AbortSignal) => Promise<Snapshot>>().mockRejectedValueOnce(new Error('403')).mockResolvedValueOnce({ version: 3, name: 'fresh' })
    const { conflict, apply, current, wrapper } = harness(fetch)
    conflict.mark(); await conflict.inspect(); expect(conflict.failed.value).toBe(true); expect(apply).not.toHaveBeenCalled()
    await conflict.inspect(); expect(conflict.failed.value).toBe(false); expect(conflict.latest.value?.version).toBe(3)
    current.value = false; conflict.applyLatest(); expect(apply).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it.each(['identity', 'token', 'permission', 'module', 'target', 'unmount'])('%s 变化中止请求，忽略不响应 abort 的迟到快照', async action => {
    let complete!: (value: Snapshot) => void
    const fetch = vi.fn<(_: string, signal: AbortSignal) => Promise<Snapshot>>().mockImplementation(() => new Promise(resolve => { complete = resolve }))
    const { conflict, wrapper, auth, modules, id, apply } = harness(fetch)
    conflict.mark(); const pending = conflict.inspect(); const signal = fetch.mock.calls[0]![1]
    if (action === 'identity') auth.applyUser({ ...auth.user!, id: 'another' })
    if (action === 'token') auth.token = 'replacement'
    if (action === 'permission') auth.applyUser({ ...auth.user!, permissions: [] })
    if (action === 'module') modules.config = { contract_version: 1, preset: 'minimal', modules: [] }
    if (action === 'target') id.value = 'another'
    if (action === 'unmount') wrapper.unmount()
    expect(signal.aborted).toBe(true)
    complete({ version: 99, name: 'private late value' }); await pending
    expect(conflict.latest.value).toBeUndefined(); conflict.applyLatest(); expect(apply).not.toHaveBeenCalled()
    if (action !== 'unmount') wrapper.unmount()
  })
  it('并发查看只发送一次，重新标记冲突清掉旧快照', async () => {
    let finish!: (value: Snapshot) => void
    const fetch = vi.fn<(_: string, signal: AbortSignal) => Promise<Snapshot>>().mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const { conflict, wrapper } = harness(fetch)
    conflict.mark(); const first = conflict.inspect(); await conflict.inspect(); expect(fetch).toHaveBeenCalledTimes(1)
    finish({ version: 2, name: 'server' }); await first; conflict.mark(); expect(conflict.latest.value).toBeUndefined(); wrapper.unmount()
  })
})

it('比较表对文本转义，使用可访问的表头和明确的替换动作', () => {
  const wrapper = mount(EditConflictPanel, { props: { loading: false, failed: false, version: 1, serverVersion: 2,
    rows: [{ label: '名字', local: '<img src=x onerror=alert(1)>', server: 'server' }] } })
  expect(wrapper.findAll('th[scope="col"]')).toHaveLength(3)
  expect(wrapper.findAll('th[scope="row"]')).toHaveLength(1)
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
  expect(wrapper.text()).toContain('载入服务器最新值（替换当前输入）'); wrapper.unmount()
})
