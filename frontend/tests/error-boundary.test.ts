import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, onMounted, ref, KeepAlive } from 'vue'
import AppErrorBoundary from '@/components/common/AppErrorBoundary.vue'
import { createErrorReporter } from '@/utils/errorReporting'

describe('全局错误边界', () => {
  it.each(['render', 'mounted'] as const)('捕获真实 %s 异常，隐藏原始信息，焦点可恢复且重试重挂载', async phase => {
    let fail = true
    let mounts = 0
    const child = defineComponent({
      setup() {
        mounts++
        onMounted(() => { if (fail && phase === 'mounted') throw new Error('token=private-password') })
        return () => { if (fail && phase === 'render') throw new Error('token=private-password'); return h('input', { value: 'fresh value', 'aria-label': '表单' }) }
      },
    })
    const reporter = createErrorReporter()
    reporter.registerRoutes(['/users'])
    const sink = vi.fn()
    reporter.configureSink(sink)
    const wrapper = mount(AppErrorBoundary, { attachTo: document.body, props: { resetKey: '/users:0', routePath: '/users', reporter }, slots: { default: () => h(child) } })
    await nextTick(); await nextTick()
    expect(wrapper.get('[role="alert"]').text()).toContain('当前未保存的输入将丢失')
    expect(wrapper.text()).not.toContain('private-password')
    expect(document.activeElement).toBe(wrapper.get('h1').element)
    expect(sink).toHaveBeenCalledOnce()
    fail = false
    await wrapper.get('.retry-button').trigger('click')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('input').element.value).toBe('fresh value')
    expect(mounts).toBe(2)
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('永久错误只在用户重试后重挂载，不自动重载；回首页由父层导航', async () => {
    let attempts = 0
    const crash = (): never => { throw new Error('private') }
    const child = defineComponent({ render() { attempts++; return crash() } })
    const wrapper = mount(AppErrorBoundary, { props: { resetKey: '/users', routePath: '/users' }, slots: { default: () => h(child) } })
    await nextTick(); await nextTick()
    expect(attempts).toBe(1)
    await wrapper.get('.retry-button').trigger('click'); await nextTick()
    expect(attempts).toBe(2)
    await wrapper.get('.error-actions button:last-child').trigger('click')
    expect(wrapper.emitted('home')).toHaveLength(1)
    expect(attempts).toBe(2)
  })

  it('路由或认证 epoch 切换重置边界，并销毁旧 KeepAlive 内容', async () => {
    const crash = ref(false)
    const route = ref('/logs')
    let mounts = 0
    const child = defineComponent({ name: 'OperationLogView', setup() { mounts++; return () => { if (crash.value) throw new Error('private'); return h('input', { value: 'fresh' }) } } })
    const wrapper = mount(AppErrorBoundary, { props: { resetKey: '/logs:0', routePath: '/logs' }, slots: { default: () => h(KeepAlive, { include: ['OperationLogView'] }, [h(child, { key: route.value })]) } })
    expect(mounts).toBe(1)
    await wrapper.get('input').setValue('unsaved')
    crash.value = true
    await nextTick(); await nextTick()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    crash.value = false
    route.value = '/users'
    await wrapper.setProps({ resetKey: '/users:1', routePath: '/users' })
    expect(wrapper.get('input').element.value).toBe('fresh')
    expect(mounts).toBe(2)
    await wrapper.setProps({ resetKey: '/users:2' })
    expect(mounts).toBe(2)
  })

  it('正常页面切换不销毁 KeepAlive 中的日志实例及未提交筛选状态', async () => {
    const route = ref('/logs')
    let logMounts = 0
    const logs = defineComponent({ name: 'OperationLogView', setup() {
      logMounts++
      const filter = ref('')
      return () => h('input', { value: filter.value, 'aria-label': '日志筛选', onInput: (event: Event) => { filter.value = (event.target as HTMLInputElement).value } })
    } })
    const other = defineComponent({ name: 'OtherView', render: () => h('div', '其他页面') })
    const wrapper = mount(AppErrorBoundary, { props: { resetKey: '/logs:0', routePath: '/logs' }, slots: {
      default: () => h(KeepAlive, { include: ['OperationLogView'] }, [h(route.value === '/logs' ? logs : other, { key: route.value })]),
    } })
    await wrapper.get('input').setValue('保留筛选')
    route.value = '/users'
    await wrapper.setProps({ resetKey: '/users:0', routePath: '/users' })
    expect(wrapper.text()).toBe('其他页面')
    route.value = '/logs'
    await wrapper.setProps({ resetKey: '/logs:0', routePath: '/logs' })
    expect(wrapper.get('input').element.value).toBe('保留筛选')
    expect(logMounts).toBe(1)
  })

  it('提供根层恢复入口但不在 UI 中显示 Error 对象', async () => {
    const wrapper = mount(AppErrorBoundary, { props: { resetKey: '/', routePath: '/' }, slots: { default: '<div>正常页面</div>' } })
    ;(wrapper.vm as unknown as { captureError: () => void }).captureError()
    await nextTick()
    expect(wrapper.find('main').attributes('aria-labelledby')).toBe('app-error-heading')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    await wrapper.setProps({ resetKey: '/settings' })
    expect(wrapper.text()).toBe('正常页面')
  })

  it('首页异常的返回首页按钮也能重挂载，重复导航不会留下旧错误', async () => {
    const wrapper = mount(AppErrorBoundary, { props: { resetKey: '/', routePath: '/' }, slots: { default: '<div>首页</div>' } })
    ;(wrapper.vm as unknown as { captureError: () => void }).captureError()
    await nextTick()
    await wrapper.get('.error-actions button:last-child').trigger('click')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toBe('首页')
    expect(wrapper.emitted('home')).toHaveLength(1)
  })
})
