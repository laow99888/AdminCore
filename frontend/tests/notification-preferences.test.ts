import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus, { ElMessage } from 'element-plus'
import NotificationPreferencesDialog from '../src/views/notifications/NotificationPreferencesDialog.vue'
import { getNotificationPreferences, saveNotificationPreferences, type NotificationPreferences } from '../src/api/notificationPreferences'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'

vi.mock('../src/api/notificationPreferences', () => ({ getNotificationPreferences: vi.fn(), saveNotificationPreferences: vi.fn() }))
const Dialog = defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue" role="dialog"><slot /><slot name="footer" /></section>' })
const initial: NotificationPreferences = {
  business_delivery_mode: 'immediate', digest_minutes: 60,
  revision: 0, subscriptions: ['announcement.update', 'template.message', 'business.update'], channels: ['inapp', 'email', 'webhook', 'sms'],
  quiet_enabled: false, quiet_start: '22:00', quiet_end: '08:00', timezone: 'Asia/Shanghai', available_channels: ['inapp'],
  events: [{ code: 'system.notice', label: '系统与安全通知', required: true },
    { code: 'approval.action', label: '审批待办与结果', required: true },
    { code: 'template.message', label: '业务模板消息', required: false }],
}
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
  vi.mocked(getNotificationPreferences).mockImplementation(async () => structuredClone(initial))
  vi.mocked(saveNotificationPreferences).mockImplementation(async body => ({ ...structuredClone(initial), ...body, revision: body.revision + 1 }))
})
async function setup(open = true) {
  const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
  auth.token = 'session'; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: false, permissions: [] }
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'notifications', title: '通知', enabled: true, dependencies: [], paths: ['/notifications'] }] }
  const wrapper = mount(NotificationPreferencesDialog, { props: { open }, global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog } } })
  await flushPromises()
  return { wrapper, auth, tenants, modules }
}
const click = async (wrapper: Awaited<ReturnType<typeof setup>>['wrapper'], text: string) => {
  await wrapper.findAll('button').find(button => button.text() === text)!.trigger('click'); await flushPromises()
}

it('仅打开时读取，关闭按钮可达；标示必达及未启用渠道', async () => {
  const { wrapper } = await setup(false)
  expect(getNotificationPreferences).not.toHaveBeenCalled()
  await wrapper.setProps({ open: true }); await flushPromises()
  expect(wrapper.text()).toContain('必须通知的站内副本始终保留')
  expect(wrapper.text()).toContain('部署未启用'); expect(wrapper.text()).toContain('站外免打扰')
  expect(wrapper.findAll('input[type="checkbox"]:disabled')).toHaveLength(2)
  await click(wrapper, '关闭'); expect(wrapper.emitted('close')).toHaveLength(1)
})
it('输入保存完整写契约，连续保存使用新版本且不发送目录字段', async () => {
  const spy = vi.spyOn(ElMessage, 'success').mockImplementation(() => ({ close: vi.fn() }))
  const { wrapper } = await setup()
  const timezone = wrapper.get('input[aria-label="时区"]')
  await timezone.setValue('UTC'); await click(wrapper, '保存')
  expect(saveNotificationPreferences).toHaveBeenCalledWith({ ...initial, timezone: 'UTC', events: undefined, available_channels: undefined }, expect.any(AbortSignal))
  const body = vi.mocked(saveNotificationPreferences).mock.calls[0]![0]
  expect(Object.keys(body)).not.toContain('events'); expect(Object.keys(body)).not.toContain('available_channels')
  expect(spy).toHaveBeenCalledWith('偏好已保存')
  await click(wrapper, '保存'); expect(vi.mocked(saveNotificationPreferences).mock.calls[1]![0].revision).toBe(1)
})
it('读取失败重试恢复', async () => {
  vi.mocked(getNotificationPreferences).mockRejectedValueOnce(new Error('offline'))
  const { wrapper } = await setup(); expect(wrapper.text()).toContain('通知偏好读取失败')
  await click(wrapper, '重试'); expect(wrapper.text()).toContain('事件订阅')
})
it('保存失败保留输入，可重新读取冲突版本', async () => {
  vi.mocked(saveNotificationPreferences).mockRejectedValueOnce(new Error('conflict'))
  const { wrapper } = await setup()
  await wrapper.get('input[aria-label="时区"]').setValue('UTC'); await click(wrapper, '保存')
  expect(wrapper.text()).toContain('输入已保留')
  expect((wrapper.get('input[aria-label="时区"]').element as HTMLInputElement).value).toBe('UTC')
  await click(wrapper, '重新读取')
  expect((wrapper.get('input[aria-label="时区"]').element as HTMLInputElement).value).toBe('Asia/Shanghai')
})
it.each(['tenant', 'session', 'user', 'module', 'password'] as const)('%s变化取消读取并忽略迟到结果', async change => {
  let resolve!: (value: NotificationPreferences) => void
  vi.mocked(getNotificationPreferences).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth, tenants, modules } = await setup()
  const signal = vi.mocked(getNotificationPreferences).mock.calls[0]![0]!
  if (change === 'tenant') tenants.currentId = 'other'
  if (change === 'session') auth.token = 'other'
  if (change === 'user') auth.user!.id = 'other'
  if (change === 'module') modules.config!.modules[0]!.enabled = false
  if (change === 'password') auth.user!.must_change_password = true
  await flushPromises(); expect(signal.aborted).toBe(true); expect(wrapper.emitted('close')).toHaveLength(1)
  resolve(initial); await flushPromises(); expect(wrapper.text()).not.toContain('事件订阅')
})
it('保存中禁止重复，身份变化取消且不展示旧成功', async () => {
  let resolve!: (value: NotificationPreferences) => void
  vi.mocked(saveNotificationPreferences).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const spy = vi.spyOn(ElMessage, 'success').mockImplementation(() => ({ close: vi.fn() }))
  const { wrapper, auth } = await setup()
  await click(wrapper, '保存'); await click(wrapper, '保存')
  expect(saveNotificationPreferences).toHaveBeenCalledTimes(1)
  const signal = vi.mocked(saveNotificationPreferences).mock.calls[0]![1]!
  auth.token = 'other'; await flushPromises(); expect(signal.aborted).toBe(true)
  resolve({ ...initial, revision: 1 }); await flushPromises(); expect(spy).not.toHaveBeenCalled()
})
it('空时区禁止保存，关闭及卸载取消读取', async () => {
  const { wrapper } = await setup()
  await wrapper.get('input[aria-label="时区"]').setValue(' ')
  await click(wrapper, '保存'); expect(saveNotificationPreferences).not.toHaveBeenCalled()
  const signal = vi.mocked(getNotificationPreferences).mock.calls[0]![0]!
  wrapper.unmount(); expect(signal.aborted).toBe(true)
})
