import { describe, expect, it, vi } from 'vitest'
import { findTrustedMicroApp, microFrontendsEnabled, trustedMicroApps } from '@/microfrontends/registry'

describe('微前端可信登记', () => {
  it('默认关闭且只接受源码登记的同源入口', () => {
    expect(microFrontendsEnabled()).toBe(false)
    expect(trustedMicroApps).toHaveLength(1)
    expect(findTrustedMicroApp('unknown')).toBeUndefined()
    expect(trustedMicroApps[0].entry).toBe('/subapps/example/')
    expect(trustedMicroApps[0].routeBase).toBe('/micro/example-subapp')
  })

  it('运行时挂载句柄可以卸载子应用', async () => {
    const unmount = vi.fn(async () => undefined)
    vi.doMock('qiankun', () => ({ loadMicroApp: () => ({ mountPromise: Promise.resolve(), unmount }) }))
    const { mountTrustedMicroApp } = await import('@/microfrontends/runtime')
    const handle = await mountTrustedMicroApp({
      app: trustedMicroApps[0], container: document.createElement('div'),
      identity: { userId: 'u1', permissions: ['example:read'], tenantId: null },
      route: '/', onNavigate: vi.fn(),
    })
    await handle.unmount()
    expect(unmount).toHaveBeenCalledOnce()
  })
})
