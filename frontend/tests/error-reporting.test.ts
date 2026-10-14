import { describe, expect, it, vi, afterEach } from 'vitest'
import { createApp, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createErrorReporter, installErrorReporting } from '@/utils/errorReporting'

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })
describe('脱敏错误上报', () => {
  it('默认关闭；只发固定白名单字段，动态路径、query与hash不透传', () => {
    const reporter = createErrorReporter()
    reporter.registerRoutes(['/', '/users', '/users/:id', '/secret?token=credential'])
    reporter.report('vue', '/users')
    const sink = vi.fn()
    reporter.configureSink(sink)
    reporter.report('vue', '/users')
    reporter.report('window', '/users?token=credential#identity')
    reporter.report('promise', '/users/private-user')
    reporter.report('navigation', '/users/:id')
    expect(sink).toHaveBeenCalledTimes(4)
    expect(sink.mock.calls[0][0].route).toBe('/users')
    for (const [event] of sink.mock.calls) {
      expect(Object.keys(event).sort()).toEqual(['category', 'correlationId', 'occurredAt', 'route'])
      expect(Object.isFrozen(event)).toBe(true)
      expect(event.occurredAt).toMatch(/^\d{4}-\d{2}-\d{2}T/)
      expect(JSON.stringify(event)).not.toMatch(/credential|identity|private-user|:id/)
    }
    expect(sink.mock.calls.slice(1).every(([event]) => event.route === 'unregistered')).toBe(true)
    reporter.configureSink(null)
    reporter.report('navigation', '/')
    expect(sink).toHaveBeenCalledTimes(4)
  })

  it('重复、递归和风暴有界，分钟窗口后可恢复', () => {
    vi.useFakeTimers()
    const reporter = createErrorReporter()
    reporter.registerRoutes(['/'])
    const sink = vi.fn(() => reporter.report('promise', '/'))
    reporter.configureSink(sink)
    for (let i = 0; i < 30; i++) reporter.report('vue', '/')
    expect(sink).toHaveBeenCalledTimes(1)
    for (let i = 0; i < 12; i++) { vi.advanceTimersByTime(5_000); reporter.report('vue', '/') }
    expect(sink).toHaveBeenCalledTimes(11) // 10 in the first minute, then the new window.
  })

  it('同步或异步 sink 失败不传播且后续仍可上报', async () => {
    vi.useFakeTimers()
    const reporter = createErrorReporter()
    reporter.configureSink(() => { throw new Error('credential must never be logged') })
    expect(() => reporter.report('vue', '/')).not.toThrow()
    reporter.configureSink(() => Promise.reject(new Error('private stack')))
    expect(() => reporter.report('window', '/')).not.toThrow()
    await new Promise<void>(resolve => queueMicrotask(resolve))
    await new Promise<void>(resolve => queueMicrotask(resolve))
    const sink = vi.fn()
    reporter.configureSink(sink)
    reporter.report('promise', '/')
    expect(sink).toHaveBeenCalledOnce()
  })

  it('未结束的异步 sink 不阻塞后续安全事件，仍受窗口总量限制', () => {
    const reporter = createErrorReporter()
    const sink = vi.fn(() => new Promise<void>(() => {}))
    reporter.configureSink(sink)
    reporter.report('vue', '/')
    reporter.report('window', '/')
    reporter.report('promise', '/')
    expect(sink).toHaveBeenCalledTimes(3)
    reporter.configureSink(null)
  })

  it('安装不重复，Vue/window/promise/router错误不读取错误对象，卸载恢复原处理器', async () => {
    const app = createApp({ render: () => h('div') })
    const original = vi.fn()
    app.config.errorHandler = original
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component: { render: () => h('div') } },
      { path: '/broken', component: () => Promise.reject(new Error('private module source')) },
    ] })
    await router.push('/')
    const reporter = createErrorReporter()
    reporter.registerRoutes(['/', '/broken'])
    const sink = vi.fn()
    reporter.configureSink(sink)
    const recovery = vi.fn()
    const dispose = installErrorReporting({ app, router, reporter, onNavigationError: recovery })
    expect(installErrorReporting({ app, router, reporter })).toBe(dispose)
    const raw = new Error('token=private-message')
    app.config.errorHandler?.(raw, null, 'private Vue context')
    window.dispatchEvent(new ErrorEvent('error', { message: raw.message, error: raw, filename: 'private-source?token=secret' }))
    window.dispatchEvent(new Event('unhandledrejection'))
    await expect(router.push('/broken')).rejects.toThrow('private module source')
    expect(sink.mock.calls.map(([event]) => event.category)).toEqual(['vue', 'window', 'promise', 'navigation'])
    expect(JSON.stringify(sink.mock.calls)).not.toMatch(/token|private|secret/)
    expect(recovery).toHaveBeenCalledOnce()
    expect(original).not.toHaveBeenCalled()
    dispose()
    expect(app.config.errorHandler).toBe(original)
    window.dispatchEvent(new Event('error'))
    window.dispatchEvent(new Event('unhandledrejection'))
    await expect(router.push('/broken')).rejects.toThrow()
    expect(sink).toHaveBeenCalledTimes(4)
    const nextDispose = installErrorReporting({ app, router, reporter, onVueError: () => { throw raw } })
    expect(() => app.config.errorHandler?.(raw, null, '')).not.toThrow()
    nextDispose()
  })
})
