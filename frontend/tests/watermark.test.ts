import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElSwitch } from 'element-plus'
import PageWatermark from '../src/components/common/PageWatermark.vue'
import WatermarkSettings from '../src/components/settings/WatermarkSettings.vue'
import { useWatermarkStore } from '../src/stores/watermark'
import { useAuthStore, type CurrentUser } from '../src/stores/auth'
import { useThemeStore } from '../src/stores/theme'

const key = 'admincore:page-watermark'
const identity: CurrentUser = { id: 'watermark-member', username: '成员', email: 'private@example.test', avatar: '' }
const watermarkEngine = { name: 'ElWatermark' }

async function setup() {
  const router = createRouter({ history: createMemoryHistory(), routes: ['/settings', '/login', '/403', '/change-password'].map(path => ({
    path, component: { template: '<div />' }, meta: { requiresAuth: path === '/settings' || path === '/change-password' },
  })) })
  await router.push('/settings')
  const auth = useAuthStore()
  auth.token = 'isolated-watermark-fixture'
  auth.applyUser(identity)
  const store = useWatermarkStore()
  const wrapper = shallowMount(PageWatermark, { global: { plugins: [router], stubs: {
    ElWatermark: { name: 'ElWatermark', props: ['content', 'font'], template: '<div />' },
  } } })
  return { router, auth, store, wrapper }
}

describe('页面水印的偏好与身份边界', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
  afterEach(() => vi.restoreAllMocks())

  it('默认关闭，启用和关闭仅持久化布尔偏好，重新创建 store 恢复', () => {
    const store = useWatermarkStore()
    expect(store.enabled).toBe(false)
    store.setEnabled(true)
    expect(localStorage.getItem(key)).toBe('true')
    expect(localStorage.length).toBe(1)
    setActivePinia(createPinia())
    const restored = useWatermarkStore()
    expect(restored.enabled).toBe(true)
    restored.setEnabled(false)
    expect(localStorage.getItem(key)).toBe('false')
  })

  it.each(['false', 'TRUE', '1', 'null', '{"enabled":true}', 'invalid'])('非法或非启用值 %s 回退关闭', value => {
    localStorage.setItem(key, value)
    expect(useWatermarkStore().enabled).toBe(false)
  })

  it('读取异常默认关闭，写入异常保留本次选择并提供可恢复的提示', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementationOnce(() => { throw new Error('blocked') })
    const store = useWatermarkStore()
    expect(store.enabled).toBe(false)
    expect(store.persistenceAvailable).toBe(false)
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    const wrapper = mount(WatermarkSettings, { global: { components: { ElSwitch } } })
    await wrapper.get('[role="switch"]').trigger('click')
    expect(store.enabled).toBe(true)
    expect(wrapper.get('[role="status"]').text()).toContain('仅在本次页面会话内生效')
    write.mockRestore()
    store.setEnabled(false)
    await nextTick()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(localStorage.getItem(key)).toBe('false')
  })

  it('有独立开关；组件不需要持有身份信息', async () => {
    const wrapper = mount(WatermarkSettings, { global: { components: { ElSwitch } } })
    expect(wrapper.get('[role="switch"]').attributes('aria-label')).toBe('启用页面水印')
    await wrapper.get('[role="switch"]').trigger('click')
    expect(useWatermarkStore().enabled).toBe(true)
    await wrapper.get('[role="switch"]').trigger('click')
    expect(useWatermarkStore().enabled).toBe(false)
    expect(localStorage.getItem(key)).toBe('false')
  })

  it('身份变更更新水印；退出及未加载身份立即移除，不保存用户名或邮箱', async () => {
    const { auth, store, wrapper } = await setup()
    expect(wrapper.findComponent(watermarkEngine).exists()).toBe(false)
    store.setEnabled(true); await nextTick(); await flushPromises()
    expect(wrapper.getComponent(watermarkEngine).props('content')).toEqual(['AdminCore', '成员'])
    auth.applyUser({ ...identity, id: 'next', username: '另一位' }); await nextTick()
    expect(wrapper.getComponent(watermarkEngine).props('content')).toEqual(['AdminCore', '另一位'])
    auth.user = null; await nextTick()
    expect(wrapper.findComponent(watermarkEngine).exists()).toBe(false)
    auth.applyUser(identity); await nextTick()
    auth.clearSession(); await nextTick()
    expect(wrapper.find('[data-testid="page-watermark"]').exists()).toBe(false)
    expect(localStorage.getItem(key)).toBe('true')
    expect(JSON.stringify({ ...localStorage })).not.toContain(identity.email)
    expect(JSON.stringify({ ...localStorage })).not.toContain(identity.username)
  })

  it('公共路由和强制改密隔离；不能在直接改密路由展示', async () => {
    const { auth, store, router, wrapper } = await setup()
    store.setEnabled(true); await nextTick(); await flushPromises()
    for (const path of ['/403', '/login', '/change-password']) {
      await router.push(path)
      expect(wrapper.findComponent(watermarkEngine).exists()).toBe(false)
    }
    await router.push('/settings')
    auth.applyUser({ ...identity, must_change_password: true }); await nextTick()
    expect(wrapper.findComponent(watermarkEngine).exists()).toBe(false)
    auth.applyUser(identity); await nextTick()
    expect(wrapper.findComponent(watermarkEngine).exists()).toBe(true)
  })

  it('用户名仅传入画布文本，截断异常长度并去掉控制符，深色切换更新绘制颜色', async () => {
    const { auth, store, wrapper } = await setup()
    store.setEnabled(true)
    auth.applyUser({ ...identity, username: '<img onerror=alert(1)>\n\u202e' + '长'.repeat(150) }); await nextTick(); await flushPromises()
    const content = wrapper.getComponent(watermarkEngine).props('content') as string[]
    expect(content[1]).toHaveLength(33)
    expect(content[1]).toContain('<img onerror=alert(1)>')
    expect(content[1]).not.toMatch(/[\n\u202e]/)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.get('[data-testid="page-watermark"]').attributes('aria-hidden')).toBe('true')
    const oldColor = wrapper.getComponent(watermarkEngine).props('font')!.color
    useThemeStore().isDark = true; await nextTick()
    expect(wrapper.getComponent(watermarkEngine).props('font')!.color).not.toBe(oldColor)
  })
})
