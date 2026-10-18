import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import FieldPolicyDiagnostics from '../src/components/common/FieldPolicyDiagnostics.vue'
import { diagnoseField, type FieldDiagnosticResult } from '../src/api/fieldDiagnostics'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'
import { i18n } from '../src/i18n'

vi.mock('../src/api/fieldDiagnostics', () => ({ diagnoseField: vi.fn() }))
const identifier = '00366522-6f05-45e1-9be8-e78ed1dca715'
const result: FieldDiagnosticResult = {
  user_id: identifier, resource: 'user', field: 'email', operation: 'read', field_action: 'read',
  field_allowed: true, field_reason: 'explicit_union', permission_code: 'user:read', operation_allowed: false,
  user_active: true, must_change_password: false, module_enabled: true, requires_admin: false,
  tenant_id: null, row_access: 'not_evaluated',
  roles: [{ id: 'role', name: '订单员', version: 4, active: true, declared: true, field_granted: true, operation_granted: false }],
  data_scope: [{ role_id: 'role', active: true, scope: 'self' }],
}
const Dialog = defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue" role="dialog"><slot /><slot name="footer" /></section>' })
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); i18n.global.locale.value = 'zh-CN'; setActivePinia(createPinia()); vi.mocked(diagnoseField).mockResolvedValue(result) })
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })
async function setup(staff = true) {
  const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
  auth.token = 'session'; auth.user = { id: identifier, username: 'admin', email: '', avatar: '', is_staff: staff, permissions: ['role:read', 'user:read'] }
  modules.config = { contract_version: 1, preset: 'standard', modules: [], field_policy_resources: { user: ['email', 'phone'], post: ['name'] } }
  const wrapper = mount(FieldPolicyDiagnostics, { props: { visible: true }, global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog } } })
  wrappers.push(wrapper); await flushPromises()
  return { wrapper, auth, tenants, modules }
}
async function run(wrapper: ReturnType<typeof mount>) { await wrapper.get('form').trigger('submit'); await flushPromises() }
it('诊断按已保存策略区分字段与功能，展示角色来源和范围但不声称记录可读', async () => {
  const { wrapper } = await setup()
  await run(wrapper)
  expect(diagnoseField).toHaveBeenCalledWith({ user_id: identifier, resource: 'user', field: 'email', operation: 'read' }, expect.any(AbortSignal))
  expect(wrapper.text()).toContain('字段策略: 允许'); expect(wrapper.text()).toContain('功能权限检查: 拒绝')
  expect(wrapper.text()).toContain('订单员'); expect(wrapper.text()).toContain('本人记录')
  expect(wrapper.text()).toContain('本结果不是写入授权')
})
it('没有管理员身份不能请求；无效用户ID禁用运行', async () => {
  const { wrapper } = await setup(false); expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(diagnoseField).not.toHaveBeenCalled()
  const admin = await setup(); await admin.wrapper.get('input[aria-label="目标用户 ID"]').setValue('invalid')
  expect(admin.wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  await run(admin.wrapper); expect(diagnoseField).not.toHaveBeenCalled()
})
it('错误保留输入，重新运行可恢复，关闭可达', async () => {
  vi.mocked(diagnoseField).mockRejectedValueOnce({ response: { status: 404 } })
  const { wrapper } = await setup(); await run(wrapper)
  expect(wrapper.text()).toContain('请检查用户 ID 和当前租户后重试')
  expect((wrapper.get('input[aria-label="目标用户 ID"]').element as HTMLInputElement).value).toBe(identifier)
  await run(wrapper); expect(wrapper.text()).toContain('订单员')
  await wrapper.findAll('button').find(button => button.text() === '关闭')!.trigger('click')
  expect(wrapper.emitted('close')).toHaveLength(1)
})
it.each(['tenant', 'session', 'permissions', 'staff', 'password', 'registry'] as const)('%s变化取消旧读取并清空旧结果和身份输入', async change => {
  let resolve!: (value: FieldDiagnosticResult) => void
  vi.mocked(diagnoseField).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth, tenants, modules } = await setup(); await run(wrapper)
  const signal = vi.mocked(diagnoseField).mock.calls[0]![1]!
  expect(wrapper.text()).toContain('正在读取当前权限')
  if (change === 'tenant') tenants.currentId = 'changed'
  if (change === 'session') auth.token = 'changed'
  if (change === 'permissions') auth.user!.permissions = []
  if (change === 'staff') auth.user!.is_staff = false
  if (change === 'password') auth.user!.must_change_password = true
  if (change === 'registry') modules.config!.field_policy_resources = { post: ['name'] }
  await flushPromises(); expect(signal.aborted).toBe(true); expect(wrapper.emitted('close')).toHaveLength(1)
  resolve(result); await flushPromises(); expect(wrapper.text()).not.toContain('订单员')
})
it('输入或关闭变化立即取消请求，迟到响应不覆盖；卸载也取消', async () => {
  let resolve!: (value: FieldDiagnosticResult) => void
  vi.mocked(diagnoseField).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper } = await setup(); await run(wrapper)
  const oldSignal = vi.mocked(diagnoseField).mock.calls[0]![1]!
  await wrapper.get('input[aria-label="目标用户 ID"]').setValue('new-input')
  expect(oldSignal.aborted).toBe(true)
  resolve(result); await flushPromises(); expect(wrapper.text()).not.toContain('订单员')
  await wrapper.get('input[aria-label="目标用户 ID"]').setValue(identifier)
  await run(wrapper); expect(wrapper.text()).toContain('订单员')
  const signal = vi.mocked(diagnoseField).mock.calls[1]![1]!
  await wrapper.setProps({ visible: false }); expect(signal.aborted).toBe(true)
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  wrapper.unmount()
})
it('管理员、兼容规则和停用状态文案提供英文且保留业务角色名', async () => {
  i18n.global.locale.value = 'en-US'
  vi.mocked(diagnoseField).mockResolvedValue({ ...result, field_reason: 'administrator', module_enabled: false,
    user_active: false, must_change_password: true, requires_admin: true, permission_code: null,
    roles: [], data_scope: [] })
  const { wrapper } = await setup(); await run(wrapper)
  expect(wrapper.text()).toContain('Administrator bypasses field restrictions')
  expect(wrapper.text()).toContain('This module is disabled'); expect(wrapper.text()).toContain('The user is inactive')
  expect(wrapper.text()).toContain('No assigned roles'); expect(wrapper.text()).toContain('This result does not authorize writes')
})
