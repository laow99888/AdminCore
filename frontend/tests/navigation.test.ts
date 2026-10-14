import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, reactive, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useNavigationStore } from '../src/stores/navigation'
import { usePageState } from '../src/composables/usePageState'

const Empty = { template: '<div />' }
async function setup() {
  const router = createRouter({ history: createMemoryHistory(), routes: ['/', '/users', '/logs'].map(path => ({ path, component: Empty, meta: { requiresAuth: true, title: path } })) })
  await router.push('/users')
  const navigation = useNavigationStore()
  navigation.ensure(router.currentRoute.value)
  return { router, navigation }
}

describe('导航与查询状态生命周期', () => {
  beforeEach(() => setActivePinia(createPinia()))
  it('去重并固定首页；不登记非业务页面或改密页', async () => {
    const { navigation, router } = await setup()
    navigation.ensure(router.currentRoute.value)
    navigation.ensure({ path: '/login', meta: {} })
    navigation.ensure({ path: '/change-password', meta: { requiresAuth: true } })
    expect(navigation.tabs.map(tab => tab.path)).toEqual(['/', '/users'])
    await navigation.close('/', router)
    expect(navigation.tabs).toHaveLength(2)
  })
  it('被离开守卫拒绝时，关闭和关闭其他都保留页签', async () => {
    const { navigation, router } = await setup()
    navigation.ensure({ path: '/logs', meta: { requiresAuth: true } })
    router.beforeEach(() => false)
    await navigation.close('/users', router)
    await navigation.closeOthers('/logs', router)
    expect(navigation.tabs.map(tab => tab.path)).toEqual(['/', '/users', '/logs'])
    expect(router.currentRoute.value.path).toBe('/users')
  })
  it('关闭页签丢弃状态，晚到的旧实例不能重新登记', async () => {
    const { navigation, router } = await setup()
    const owner = navigation.generation('/logs')
    navigation.ensure({ path: '/logs', meta: { requiresAuth: true } })
    navigation.remember('/logs', { page: 3 }, owner)
    await navigation.close('/logs', router)
    navigation.remember('/logs', { page: 4 }, owner)
    expect(navigation.query('/logs')).toBeUndefined()
    expect(navigation.generation('/logs')).not.toBe(owner)
  })
  it('撤权清除页签和状态，切换会话后拒绝旧组件写回', async () => {
    const { navigation } = await setup()
    const owner = navigation.generation('/users')
    navigation.remember('/users', { search: 'private' }, owner)
    navigation.prune(path => path === '/')
    expect(navigation.query('/users')).toBeUndefined()
    expect(navigation.tabs.map(tab => tab.path)).toEqual(['/'])
    navigation.clear()
    navigation.remember('/users', { search: 'private' }, owner)
    expect(navigation.query('/users')).toBeUndefined()
    expect(navigation.tabs).toEqual([])
  })
  it('只保存登记的筛选与页码，重新挂载恢复克隆值', async () => {
    const { navigation, router } = await setup()
    const View = defineComponent({ setup() {
      const page = ref(1), filters = reactive({ search: '', active: null as boolean | null })
      usePageState({ page, filters })
      return { page, filters }
    }, template: '<div />' })
    const first = mount(View, { global: { plugins: [router] } })
    first.vm.page = 3
    first.vm.filters.search = 'member'
    first.vm.filters.active = false
    first.unmount()
    // The last mounted test app uninstalls/reset the memory router; restore its location.
    await router.push('/users')
    const second = mount(View, { global: { plugins: [router] } })
    expect(second.vm.page).toBe(3)
    expect(second.vm.filters).toEqual({ search: 'member', active: false })
    expect(navigation.query('/users')).toEqual({ page: 3, filters: { search: 'member', active: false } })
    expect(localStorage.getItem('admincore:navigation-tabs')).toBeNull()
    expect(sessionStorage.getItem('admincore:navigation-tabs')).toBeNull()
  })
})
