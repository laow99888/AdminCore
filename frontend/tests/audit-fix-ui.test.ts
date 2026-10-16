import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElAutocomplete } from 'element-plus'
import { realtimeUrl } from '../src/api/baseUrl'
import { useAuthStore } from '../src/stores/auth'
import { menusApi } from '../src/api'
import MenuSearch from '../src/components/layout/MenuSearch.vue'

vi.mock('../src/api', () => ({ menusApi: { myMenu: vi.fn() } }))
vi.mock('../src/stores/modules', () => ({ useModuleStore: () => ({ config: {}, pagePermissions: {}, pathEnabled: (path: string) => path !== '/files' }) }))

describe('审查修复：搜索和 SSE 地址', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); vi.clearAllMocks() })
  it('SSE 复用相同 API 路径，并阻止向跨源地址发送凭据', () => {
    expect(realtimeUrl('/custom/v2/', 'https://example.test')).toBe('/custom/v2/realtime/events/')
    expect(realtimeUrl('https://example.test/api/v2', 'https://example.test')).toBe('/api/v2/realtime/events/')
    for (const base of ['https://other.test/api', '//other.test/api', '/api?token=x', '/api#x', 'https://user:pass@example.test/api']) {
      expect(() => realtimeUrl(base, 'https://example.test')).toThrow()
    }
  })
  it('搜索仅返回有权限且启用的实际路由，选择后跳转；撤权后重新校验', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: ['/', '/users', '/roles', '/files'].map(path => ({ path, component: { template: '<div />' }, meta: { requiresAuth: true } })) })
    await router.push('/')
    const auth = useAuthStore()
    auth.applyUser({ id: 'search-user', username: 'search', email: '', avatar: '', permissions: ['user:read', 'file:read'] })
    vi.mocked(menusApi.myMenu).mockResolvedValue([
      { name: '用户管理', path: '/users' }, { name: '角色管理', path: '/roles' },
      { name: '文件管理', path: '/files' }, { name: '隐藏菜单', path: '/users', is_visible: false },
      { name: '恶意菜单', path: '//example.test' },
    ] as Awaited<ReturnType<typeof menusApi.myMenu>>)
    const wrapper = mount(MenuSearch, { global: { plugins: [router] } })
    const control = wrapper.findAllComponents(ElAutocomplete)[0]!
    type Item = { value: string; path: string }
    const results = vi.fn<(items: Item[]) => void>()
    const { fetchSuggestions: suggest } = control.props() as { fetchSuggestions: (query: string, done: typeof results) => Promise<void> }
    await suggest('管理', results)
    expect(results).toHaveBeenLastCalledWith([expect.objectContaining({ path: '/users' })])
    control.vm.$emit('select', { path: '/users' }); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/users')
    auth.applyUser({ ...auth.user!, permissions: [] }); await flushPromises()
    await router.push('/')
    control.vm.$emit('select', { path: '/users' }); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/')
    await suggest('用户', results)
    expect(results).toHaveBeenLastCalledWith([])
  })
})
