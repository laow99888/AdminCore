import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import BusinessSearch from '../src/components/layout/BusinessSearch.vue'
import request from '../src/api/request'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'

vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api/request', () => ({ default: { get: vi.fn() } }))
const Dialog = defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue"><slot /></section>' })
const wrappers: ReturnType<typeof mount>[] = []
const id = '12345678-1234-4234-8234-123456789abc'
const group = { source: 'orders', title: '订单', path: '/orders', has_more: true,
  items: [{ id, title: '采购单甲', values: [{ label: '编码', value: '<script>private</script>' }] }] }
const result = (groups = [group], sources_limited = false) => ({ data: { data: { groups, sources_limited } } })
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia()); vi.mocked(request.get).mockResolvedValue(result()) })
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.useRealTimers() })
async function setup() {
  const auth = useAuthStore(), modules = useModuleStore(), tenants = useTenantStore()
  auth.token = 'search-session'; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: false, permissions: ['orders:read'] }
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'orders', title: '订单', enabled: true, dependencies: [], paths: ['/orders'], page_permissions: { '/orders': 'orders:read' } }] }
  const router = createRouter({ history: createMemoryHistory(), routes: ['/', '/orders'].map(path => ({ path, component: { template: '<div />' }, meta: { requiresAuth: true } })) })
  await router.push('/')
  const wrapper = mount(BusinessSearch, { global: { plugins: [router, ElementPlus], stubs: { ElDialog: Dialog } } }); wrappers.push(wrapper)
  await wrapper.get('button[aria-label="业务搜索"]').trigger('click')
  return { wrapper, auth, modules, tenants, router }
}
async function run(wrapper: ReturnType<typeof mount>, keyword = '采购') {
  await wrapper.get('input').setValue(keyword); await wrapper.get('form').trigger('submit'); await flushPromises()
}

it('只在输入足够关键词后搜索，展示有界结果和转义摘要，点击使用登记路径和记录ID', async () => {
  const { wrapper, router } = await setup()
  expect(request.get).not.toHaveBeenCalled()
  await run(wrapper, 'a'); expect(request.get).not.toHaveBeenCalled()
  await run(wrapper)
  expect(request.get).toHaveBeenCalledWith('/business-search/', { params: { q: '采购' }, signal: expect.any(AbortSignal) })
  expect(wrapper.text()).toContain('最近5条')
  expect(wrapper.find('script').exists()).toBe(false)
  await wrapper.get('.business-search-record').trigger('click'); await flushPromises()
  expect(router.currentRoute.value.query.record).toBe(id)
  expect(router.currentRoute.value.path).toBe('/orders')
})

it('查询变化立即清除旧结果，防抖只发送最后一个关键词', async () => {
  const { wrapper } = await setup(); vi.useFakeTimers()
  await wrapper.get('input').setValue('采购'); await vi.advanceTimersByTimeAsync(150)
  await wrapper.get('input').setValue('采购单'); await vi.advanceTimersByTimeAsync(301); await flushPromises()
  expect(request.get).toHaveBeenCalledTimes(1)
  expect(request.get).toHaveBeenLastCalledWith('/business-search/', expect.objectContaining({ params: { q: '采购单' } }))
  await wrapper.get('input').setValue('另一个'); expect(wrapper.find('.business-search-record').exists()).toBe(false)
})

it('后发请求先完成时，旧响应不能覆盖新结果且已发送取消信号', async () => {
  let resolve!: (value: unknown) => void
  vi.mocked(request.get).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper } = await setup(); await run(wrapper)
  const signal = vi.mocked(request.get).mock.calls[0]![1]!.signal as AbortSignal
  await run(wrapper, '新的'); expect(signal.aborted).toBe(true)
  resolve(result([{ ...group, items: [{ ...group.items[0]!, title: '旧敏感摘要' }] }])); await flushPromises()
  expect(wrapper.text()).not.toContain('旧敏感摘要')
  expect(wrapper.text()).toContain('采购单甲')
})

it.each(['tenant', 'permission', 'session', 'module', 'password'] as const)('%s上下文变化关闭并清空结果，拒绝迟到响应', async change => {
  let resolve!: (value: unknown) => void
  vi.mocked(request.get).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth, modules, tenants } = await setup(); await run(wrapper)
  if (change === 'tenant') tenants.currentId = 'new-tenant'
  if (change === 'permission') auth.user!.permissions = []
  if (change === 'session') auth.token = 'different-session'
  if (change === 'module') modules.config!.modules[0]!.enabled = false
  if (change === 'password') auth.user!.must_change_password = true
  await flushPromises(); resolve(result()); await flushPromises()
  expect(wrapper.find('form').exists()).toBe(false)
  await wrapper.get('button[aria-label="业务搜索"]').trigger('click')
  expect(wrapper.get('input').element.value).toBe('')
  expect(wrapper.text()).not.toContain('采购单甲')
})

it('空状态、来源上限、失败重试有明确反馈，重新提交可恢复', async () => {
  const { wrapper } = await setup()
  vi.mocked(request.get).mockResolvedValueOnce(result([]))
  await run(wrapper); expect(wrapper.text()).toContain('没有匹配的授权业务记录')
  vi.mocked(request.get).mockRejectedValueOnce(new Error('offline'))
  await run(wrapper); expect(wrapper.text()).toContain('业务搜索失败')
  const retry = wrapper.findAll('button').find(button => button.text() === '重试')!
  vi.mocked(request.get).mockResolvedValueOnce(result([group], true))
  await retry.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('最多搜索8个来源')
  expect(wrapper.text()).toContain('采购单甲')
})

it('响应中不可访问路由或外站路径不展示，卸载取消请求并丢弃结果', async () => {
  vi.mocked(request.get).mockResolvedValueOnce(result([{ ...group, path: '//evil.test' }]))
  const { wrapper } = await setup(); await run(wrapper)
  expect(wrapper.text()).not.toContain('采购单甲')
  let resolve!: (value: unknown) => void
  vi.mocked(request.get).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  await run(wrapper); const signal = vi.mocked(request.get).mock.calls.at(-1)![1]!.signal as AbortSignal
  wrapper.unmount(); expect(signal.aborted).toBe(true); resolve(result()); await flushPromises()
})
