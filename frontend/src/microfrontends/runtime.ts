import { loadMicroApp, type MicroApp } from 'qiankun'
import type { TrustedMicroApp } from './registry'

export interface MicroAppIdentity {
  userId: string
  permissions: string[]
  tenantId: string | null
}

export interface MountTrustedMicroAppOptions {
  app: TrustedMicroApp
  container: HTMLElement
  identity: MicroAppIdentity
  route: string
  onNavigate: (path: string) => void
}

export interface MountedMicroApp {
  unmount: () => Promise<void>
}

/** 运行时句柄只保留在宿主，卸载由 Vue 生命周期显式触发。 */
export async function mountTrustedMicroApp(options: MountTrustedMicroAppOptions): Promise<MountedMicroApp> {
  const microApp: MicroApp = loadMicroApp({
    name: options.app.name,
    entry: options.app.entry,
    container: options.container,
    props: {
      // 身份摘要可用于渲染；访问/刷新令牌永远不作为 props 传递。
      identity: options.identity,
      initialRoute: options.route,
      onHostNavigate: options.onNavigate,
    },
  }, { sandbox: { strictStyleIsolation: true } })
  await microApp.mountPromise
  return { unmount: async () => { await microApp.unmount() } }
}
