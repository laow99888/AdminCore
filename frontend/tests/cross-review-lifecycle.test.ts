import { afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useModuleStore } from '@/stores/modules'
import request from '@/api/request'
import * as registry from '@/microfrontends/registry'
import * as runtime from '@/microfrontends/runtime'
import MicroAppView from '@/views/microfrontends/MicroAppView.vue'
import { useRowKey } from '@/composables/useRowKey'

afterEach(() => vi.restoreAllMocks())
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
it('旧会话的模块响应不得覆盖新用户，租户切换也清空缓存', async () => {
  setActivePinia(createPinia())
  const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
  auth.user = { id: 'a', permissions: ['*'] } as never
  const first = deferred<never>(), second = deferred<never>()
  vi.spyOn(request, 'get').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
  const old = modules.load()
  auth.user = { id: 'b', permissions: ['*'] } as never
  const current = modules.load()
  second.resolve({ data: { data: { contract_version: 1, preset: 'b', modules: [] } } } as never)
  await current
  first.resolve({ data: { data: { contract_version: 1, preset: 'a', modules: [] } } } as never)
  await old
  expect(modules.config?.preset).toBe('b')
  tenants.currentId = 'another-tenant'
  expect(modules.config).toBeNull()
  auth.user = null
  expect(modules.config).toBeNull()
})
it('离开页面后才完成挂载的子应用必须卸载', async () => {
  const pinia = createPinia(); setActivePinia(pinia)
  useAuthStore().user = { id: 'a', permissions: ['*'] } as never
  vi.spyOn(registry, 'microFrontendsEnabled').mockReturnValue(true)
  const pending = deferred<runtime.MountedMicroApp>()
  vi.spyOn(runtime, 'mountTrustedMicroApp').mockReturnValue(pending.promise)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/micro/:appKey', component: MicroAppView }] })
  await router.push('/micro/example-subapp')
  const wrapper = mount(MicroAppView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  expect(runtime.mountTrustedMicroApp).toHaveBeenCalledOnce()
  wrapper.unmount()
  const unmount = vi.fn().mockResolvedValue(undefined)
  pending.resolve({ unmount })
  await flushPromises()
  expect(unmount).toHaveBeenCalledOnce()
})
it('删除中间明细后，剩余对象的组件 key 保持不变', () => {
  const key = useRowKey(), rows = [{ name: 'a' }, { name: 'b' }, { name: 'c' }]
  const original = rows.map(key)
  rows.splice(1, 1)
  expect(rows.map(key)).toEqual([original[0], original[2]])
  expect(key({ name: 'c' })).not.toBe(original[2])
})
