import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import NotificationDigestDialog from '../src/views/notifications/NotificationDigestDialog.vue'
import BusinessNoticeSendDialog from '../src/views/notifications/BusinessNoticeSendDialog.vue'
import { notificationDigestsApi } from '../src/api/notificationDigests'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'
const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', async importOriginal => ({ ...await importOriginal<object>(), useRouter: () => ({ push, resolve: () => ({ matched: [{ meta: { requiresAuth: true } }] }) }) }))
vi.mock('../src/api/notificationDigests', () => ({ notificationDigestsApi: { status: vi.fn(), refresh: vi.fn(), detail: vi.fn(), operations: vi.fn(), send: vi.fn(), search: vi.fn() } }))
const Dialog = defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue" role="dialog"><slot /><slot name="footer" /></section>' })
const PersonPicker = defineComponent({ emits: ['update:modelValue'], template: '<button @click="$emit(\'update:modelValue\', { id: \'recipient\' })">选择测试收件人</button>' })
const wrappers: ReturnType<typeof mount>[] = []
const refRow = { resource: 'orders', label: '订单', object_id: '11111111-1111-4111-8111-111111111111', path: '/orders' }
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
  vi.mocked(notificationDigestsApi.status).mockResolvedValue({ pending: 2, due: 1, next_due_at: null })
  vi.mocked(notificationDigestsApi.refresh).mockResolvedValue({ processed: 1, published: 1, suppressed: 0, summaries: 1 })
  vi.mocked(notificationDigestsApi.detail).mockResolvedValue({ items: [refRow], authorization_checked_at: 'now' })
  vi.mocked(notificationDigestsApi.operations).mockResolvedValue({ window_days: 7, since: 'start', until: 'end', inbox_created: 3, inbox_read: 1, due_notices: 1, deliveries: [{ channel: 'email', status: 'succeeded', count: 1 }], outbox: [], business_notices: [], final_delivery_receipts_supported: false })
  vi.mocked(notificationDigestsApi.search).mockResolvedValue([{ source: 'orders', title: '订单', path: '/orders', items: [{ id: refRow.object_id, title: '采购一' }] }])
  vi.mocked(notificationDigestsApi.send).mockResolvedValue({ created: 1, replayed: 0, pending: 1, published: 0, suppressed: 0 })
})
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))
async function setup(kind: 'status' | 'detail' | 'send' = 'status', staff = true) {
  const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
  auth.token = 'session'; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: staff, permissions: ['template:read', 'template:send', 'orders:read'] }
  modules.config = { contract_version: 1, preset: 'standard', modules: ['notifications', 'orders'].map(key => ({ key, title: key, enabled: true, dependencies: [], paths: [`/${key}`] })) }
  const wrapper = kind === 'send' ? mount(BusinessNoticeSendDialog, { props: { open: true }, global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog, PersonPicker } } })
    : mount(NotificationDigestDialog, { props: { open: true, notificationId: kind === 'detail' ? 'notice' : undefined }, global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog } } })
  wrappers.push(wrapper); await flushPromises(); return { wrapper, auth, tenants, modules }
}
async function click(wrapper: ReturnType<typeof mount>, text: string) { await wrapper.findAll('button').find(row => row.text() === text)!.trigger('click'); await flushPromises() }

it('本人到期摘要刷新后更新状态；运营统计说明不保证供应商最终送达', async () => {
  const { wrapper } = await setup()
  await click(wrapper, '合并我的到期提醒')
  expect(notificationDigestsApi.refresh).toHaveBeenCalledTimes(1)
  expect(wrapper.emitted('refreshed')).toHaveLength(1)
  await click(wrapper, '读取统计')
  expect(notificationDigestsApi.operations).toHaveBeenCalledWith(7, expect.any(AbortSignal))
  expect(wrapper.text()).toContain('当前不提供供应商最终送达回执')
  expect(wrapper.text()).toContain('渠道执行完成')
})
it('合并进行中禁止刷新状态，完成后自动重读并恢复合并按钮', async () => {
  let resolve!: (value: Awaited<ReturnType<typeof notificationDigestsApi.refresh>>) => void
  vi.mocked(notificationDigestsApi.refresh).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper } = await setup()
  await click(wrapper, '合并我的到期提醒')
  const signal = vi.mocked(notificationDigestsApi.refresh).mock.calls[0]![0]!
  const statusButton = wrapper.findAll('button').find(row => row.text() === '刷新状态')!
  expect(statusButton.attributes('disabled')).toBeDefined()
  await statusButton.trigger('click'); await flushPromises()
  expect(signal.aborted).toBe(false)
  expect(notificationDigestsApi.status).toHaveBeenCalledTimes(1)
  resolve({ processed: 1, published: 1, suppressed: 0, summaries: 1 }); await flushPromises()
  expect(notificationDigestsApi.status).toHaveBeenCalledTimes(2)
  expect(wrapper.emitted('refreshed')).toHaveLength(1)
  const mergeButton = wrapper.findAll('button').find(row => row.text() === '合并我的到期提醒')!
  expect(mergeButton.attributes('disabled')).toBeUndefined()
  expect(mergeButton.classes()).not.toContain('is-loading')
  await click(wrapper, '合并我的到期提醒')
  expect(notificationDigestsApi.refresh).toHaveBeenCalledTimes(2)
})
it('普通人员没有运营入口；状态失败可重试', async () => {
  vi.mocked(notificationDigestsApi.status).mockRejectedValueOnce(new Error('offline'))
  const { wrapper } = await setup('status', false)
  expect(wrapper.text()).not.toContain('通知运营统计')
  expect(wrapper.text()).toContain('摘要读取失败')
  await click(wrapper, '刷新状态'); expect(wrapper.text()).toContain('等待摘要')
})
it('点击摘要回链重新鉴权；撤权结果为空时不导航', async () => {
  const { wrapper } = await setup('detail')
  vi.mocked(notificationDigestsApi.detail).mockResolvedValueOnce({ items: [], authorization_checked_at: 'later' })
  await click(wrapper, '订单 · 查看业务记录')
  expect(push).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('没有当前可访问')
})
it('合法回链携带记录标识进入已授权业务页', async () => {
  const { wrapper } = await setup('detail')
  await click(wrapper, '订单 · 查看业务记录')
  expect(push).toHaveBeenCalledWith({ path: '/orders', query: { record: refRow.object_id } })
})
it.each(['tenant', 'session', 'permissions'])('%s变化取消读取并忽略迟到摘要', async change => {
  let resolve!: (value: Awaited<ReturnType<typeof notificationDigestsApi.detail>>) => void
  vi.mocked(notificationDigestsApi.detail).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth, tenants } = await setup('detail')
  const signal = vi.mocked(notificationDigestsApi.detail).mock.calls[0]![1]!
  if (change === 'tenant') tenants.currentId = 'other'
  if (change === 'session') auth.token = 'other'
  if (change === 'permissions') auth.user!.permissions = []
  await flushPromises(); expect(signal.aborted).toBe(true); expect(wrapper.emitted('close')).toHaveLength(1)
  resolve({ items: [refRow], authorization_checked_at: 'late' }); await flushPromises()
  expect(wrapper.text()).not.toContain('订单')
})
it('业务提醒失败保留选择，重试复用事件标识并阻止成功后重复发送', async () => {
  vi.mocked(notificationDigestsApi.send).mockRejectedValueOnce(new Error('offline'))
  const { wrapper } = await setup('send')
  await wrapper.get('input[aria-label="搜索业务记录"]').setValue('采购'); await click(wrapper, '搜索')
  await wrapper.get('input[type="radio"]').setValue(); await click(wrapper, '选择测试收件人')
  await click(wrapper, '发送业务提醒'); expect(wrapper.text()).toContain('选择已保留')
  const first = vi.mocked(notificationDigestsApi.send).mock.calls[0]![0]
  await click(wrapper, '发送业务提醒')
  expect(vi.mocked(notificationDigestsApi.send).mock.calls[1]![0]).toEqual(first)
  expect(wrapper.emitted('sent')).toHaveLength(1)
  expect(wrapper.findAll('button').find(row => row.text() === '发送业务提醒')!.attributes('disabled')).toBeDefined()
})
