import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElSwitch } from 'element-plus'
import KeyboardShortcuts from '../src/components/common/KeyboardShortcuts.vue'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useNavigationStore } from '../src/stores/navigation'
import { handleKeyboardShortcut, installKeyboardShortcuts, KEYBOARD_HELP_EVENT, KEYBOARD_SHORTCUTS_KEY, readKeyboardPreference, writeKeyboardPreference, type ShortcutContext } from '../src/utils/keyboardShortcuts'

const mounted: ReturnType<typeof mount>[] = []
beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
afterEach(() => { mounted.splice(0).forEach(wrapper => wrapper.unmount()); document.body.innerHTML = ''; vi.restoreAllMocks() })
function context(overrides: Partial<ShortcutContext> = {}): ShortcutContext {
  return { enabled: true, active: true, path: '/users', tabs: [{ path: '/' }, { path: '/users' }, { path: '/settings' }],
    allowed: () => true, navigate: vi.fn(), close: vi.fn(), help: vi.fn(), ...overrides }
}
function key(key: string, init: KeyboardEventInit = {}) { return new KeyboardEvent('keydown', { key, altKey: true, shiftKey: true, cancelable: true, bubbles: true, ...init }) }
const run = (event: KeyboardEvent, ctx = context()) => handleKeyboardShortcut(event, ctx, document)

describe('快捷键命令与浏览器边界', () => {
  it('默认关闭，非法值不启用；只保存布尔偏好', () => {
    expect(readKeyboardPreference(localStorage).enabled).toBe(false)
    for (const value of ['TRUE', '1', '{}']) { localStorage.setItem(KEYBOARD_SHORTCUTS_KEY, value); expect(readKeyboardPreference(localStorage).enabled).toBe(false) }
    expect(writeKeyboardPreference(localStorage, true)).toBe(true)
    expect(readKeyboardPreference(localStorage)).toEqual({ enabled: true, persistenceAvailable: true })
    expect(writeKeyboardPreference(localStorage, false)).toBe(true)
    expect(localStorage.getItem(KEYBOARD_SHORTCUTS_KEY)).toBe('false')
  })
  it('存储异常安全回退并反馈保存失败', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    expect(readKeyboardPreference(localStorage)).toEqual({ enabled: false, persistenceAvailable: false })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    expect(writeKeyboardPreference(localStorage, true)).toBe(false)
  })
  it.each([['H', '/'], ['s', '/settings'], ['ArrowLeft', '/'], ['ArrowRight', '/settings']])('%s 普通路由导航到 %s', (value, path) => {
    const ctx = context(), event = key(value)
    expect(run(event, ctx)).toBe(true)
    expect(ctx.navigate).toHaveBeenCalledExactlyOnceWith(path)
    expect(event.defaultPrevented).toBe(true)
  })
  it('关闭调用现有关闭守卫；首页、无目标、相同路由和无权限不占用按键', () => {
    const ctx = context()
    expect(run(key('w'), ctx)).toBe(true)
    expect(ctx.close).toHaveBeenCalledExactlyOnceWith('/users')
    expect(run(key('h'), context({ path: '/' }))).toBe(false)
    expect(run(key('w'), context({ path: '/' }))).toBe(false)
    expect(run(key('ArrowRight'), context({ path: '/settings' }))).toBe(false)
    expect(run(key('s'), context({ allowed: () => false }))).toBe(false)
    expect(run(key('w'), context({ allowed: path => path === '/users' }))).toBe(false)
  })
  it('禁用、公共页、组合键冲突、自动重复和组合输入不拦截', () => {
    for (const ctx of [context({ enabled: false }), context({ active: false })]) expect(run(key('h'), ctx)).toBe(false)
    for (const init of [{ ctrlKey: true }, { metaKey: true }, { repeat: true }, { isComposing: true }, { shiftKey: false }, { keyCode: 229 }]) expect(run(key('h', init))).toBe(false)
    const prevented = key('h'); prevented.preventDefault()
    expect(run(prevented)).toBe(false)
    expect(run(key('?', { altKey: false }))).toBe(true)
    expect(run(key('?', { altKey: false, ctrlKey: true }))).toBe(false)
  })
  it.each(['input', 'textarea', 'select', 'div[contenteditable="true"]', 'div[role="textbox"]', 'div[role="combobox"]', 'div[role="spinbutton"]'])('编辑控件 %s 不拦截', selector => {
    const html = selector.replace(/\[([^=]+)="([^"]+)"\]/, ' $1="$2"'), tag = selector.split('[')[0]
    document.body.innerHTML = `<${html}></${tag}>`
    const ctx = context(), event = key('s')
    document.body.firstElementChild!.addEventListener('keydown', value => run(value as KeyboardEvent, ctx))
    document.body.firstElementChild!.dispatchEvent(event)
    expect(ctx.navigate).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })
  it('可见弹窗/菜单拦截，隐藏遗留菜单不影响快捷键', () => {
    const overlay = document.createElement('div'); overlay.setAttribute('role', 'dialog'); document.body.append(overlay)
    const rectangles = vi.spyOn(overlay, 'getClientRects').mockReturnValue([{ width: 100 }] as unknown as DOMRectList)
    expect(run(key('h'))).toBe(false)
    overlay.style.visibility = 'hidden'
    expect(run(key('h'))).toBe(true)
    overlay.style.visibility = ''; rectangles.mockReturnValue([] as unknown as DOMRectList)
    expect(run(key('h'))).toBe(true)
  })
  it('同一窗口只保留一个监听器，旧卸载不移除新实例；帮助入口在关闭偏好时可用', () => {
    const first = context(), second = context({ enabled: false })
    const firstHelp = vi.fn(), secondHelp = vi.fn()
    const stopFirst = installKeyboardShortcuts(window, () => first, firstHelp)
    const stopSecond = installKeyboardShortcuts(window, () => second, secondHelp)
    stopFirst()
    window.dispatchEvent(new Event(KEYBOARD_HELP_EVENT))
    expect(firstHelp).not.toHaveBeenCalled(); expect(secondHelp).toHaveBeenCalledOnce()
    second.enabled = true; window.dispatchEvent(key('h'))
    expect(first.navigate).not.toHaveBeenCalled(); expect(second.navigate).toHaveBeenCalledOnce()
    stopSecond(); window.dispatchEvent(key('h'))
    expect(second.navigate).toHaveBeenCalledOnce()
  })
})

const Dialog = defineComponent({ props: ['modelValue'], setup: (props, { slots }) => () => props.modelValue ? h('section', { role: 'dialog' }, [slots.default?.(), slots.footer?.()]) : null })
async function setup(enabled = true) {
  localStorage.setItem(KEYBOARD_SHORTCUTS_KEY, String(enabled))
  const router = createRouter({ history: createMemoryHistory(), routes: ['/', '/users', '/settings', '/files', '/login', '/change-password'].map(path => ({ path,
    component: { template: '<div />' }, meta: { requiresAuth: path !== '/login', title: path } })) })
  await router.push('/users')
  const auth = useAuthStore(); auth.token = 'isolated-shortcut-fixture'
  auth.applyUser({ id: 'shortcut-member', username: 'member', email: '', avatar: '', permissions: ['*'] })
  const modules = useModuleStore(); modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'files', title: '', enabled: true, paths: ['/files'], dependencies: [] }] }
  const navigation = useNavigationStore(); navigation.ensure(router.currentRoute.value)
  navigation.ensure({ path: '/files', meta: { requiresAuth: true, title: 'files' } })
  const wrapper = mount(KeyboardShortcuts, { attachTo: document.body, global: { plugins: [router], components: { ElSwitch }, stubs: { ElDialog: Dialog, ElButton: { template: '<button><slot /></button>' } } } })
  mounted.push(wrapper)
  return { router, auth, modules, navigation, wrapper }
}

describe('快捷键根组件的会话、权限与路由守卫', () => {
  it('关闭偏好仍可开帮助与启用，保存失败仍本次生效', async () => {
    const { wrapper, router } = await setup(false)
    window.dispatchEvent(new Event(KEYBOARD_HELP_EVENT)); await nextTick()
    expect(wrapper.text()).toContain('默认关闭')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    await wrapper.get('.el-switch').trigger('click')
    expect(wrapper.get('[role="status"]').text()).toContain('仅在本次页面会话内生效')
    await wrapper.get('button').trigger('click'); await nextTick()
    window.dispatchEvent(key('s')); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/settings')
  })
  it('普通切换与关闭均服从离开守卫，被拒绝后页签完整', async () => {
    const { router, navigation } = await setup()
    router.beforeEach(() => false)
    window.dispatchEvent(key('h')); await flushPromises()
    window.dispatchEvent(key('w')); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/users')
    expect(navigation.tabs.map(tab => tab.path)).toEqual(['/', '/users', '/files'])
  })
  it('模块禁用/权限撤销后不访问相邻页；认证失效、公共页与强制改密不响应帮助', async () => {
    const { router, auth, modules, wrapper } = await setup()
    modules.config!.modules[0]!.enabled = false
    const denied = key('ArrowRight'); window.dispatchEvent(denied); await flushPromises()
    expect(denied.defaultPrevented).toBe(false)
    modules.config!.modules[0]!.enabled = true
    auth.user!.permissions = []
    const close = key('w'); window.dispatchEvent(close)
    expect(close.defaultPrevented).toBe(false)
    auth.user!.must_change_password = true
    window.dispatchEvent(new Event(KEYBOARD_HELP_EVENT)); await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    auth.user!.must_change_password = false
    await router.push('/login'); window.dispatchEvent(new Event(KEYBOARD_HELP_EVENT)); await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await router.push('/users'); auth.clearSession(); window.dispatchEvent(new Event(KEYBOARD_HELP_EVENT)); await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
  it('登出即关闭帮助，组件卸载清理监听，拒绝后续事件', async () => {
    const { auth, wrapper, router } = await setup()
    window.dispatchEvent(new Event(KEYBOARD_HELP_EVENT)); await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    auth.clearSession(); await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    auth.token = 'isolated-shortcut-fixture'
    auth.applyUser({ id: 'shortcut-member', username: 'member', email: '', avatar: '', permissions: ['*'] })
    wrapper.unmount(); mounted.splice(mounted.indexOf(wrapper), 1)
    await router.push('/users')
    const navigate = vi.spyOn(router, 'push')
    window.dispatchEvent(key('s')); await flushPromises()
    expect(navigate).not.toHaveBeenCalled()
  })
})
