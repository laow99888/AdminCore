import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import { useAuthStore } from '../src/stores/auth'
import { useTenantStore } from '../src/stores/tenants'
import { approvalDiagnosticsApi, type ApprovalDiagnostic } from '../src/api/approvalDiagnostics'
import Diagnostics from '../src/views/approvals/ApprovalDiagnostics.vue'
import Calendar from '../src/views/approvals/WorkingCalendarEditor.vue'
import { validateWorkingCalendar, type WorkingCalendar } from '../src/views/approvals/workingCalendar'
vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value, registerUiMessages: vi.fn() }))
vi.mock('../src/api/approvalDiagnostics', () => ({ approvalDiagnosticsApi: { request: vi.fn(), health: vi.fn() } }))
const calendar: WorkingCalendar = { timezone: 'Asia/Shanghai', weekdays: [1, 2, 3, 4, 5], start: '09:00', end: '18:00', closed_dates: ['2026-10-01'], extra_dates: ['2026-10-10'] }
const diagnostic: ApprovalDiagnostic = { request_id: 'application', workflow_version: 3, checked_at: '2026-10-19T09:00', scope: 'current', blocked: true, issues: [{ code: 'assignee_unavailable', severity: 'blocked', node: 'first', step_id: 'step', step_version: 2 }] }
beforeEach(() => vi.resetAllMocks())
afterEach(() => localStorage.clear())
async function setup(admin = true, props = {}) {
 const pinia = createPinia(), auth = useAuthStore(pinia), tenant = useTenantStore(pinia)
 auth.token = 'diagnostics'; auth.user = { id: 'admin', username: 'admin', email: '', avatar: '', permissions: ['*'], is_staff: admin }
 const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] }); await router.push('/')
 const wrapper = mount(Diagnostics, { props, global: { plugins: [pinia, router, ElementPlus] } })
 const button = (text: string) => wrapper.findAll('button').find(node => node.text() === text)!
 return { wrapper, auth, tenant, button }
}
it('日历开关产生默认工作日，不修改传入对象，发布态全部只读', async () => {
 const wrapper = mount(Calendar, { props: { modelValue: null }, global: { plugins: [ElementPlus] } })
 await wrapper.get('[role="switch"]').trigger('click')
 expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toEqual({ ...calendar, closed_dates: [], extra_dates: [] })
 await wrapper.setProps({ modelValue: calendar })
 await wrapper.get('input[aria-label="日历时区"]').setValue('UTC')
 expect(calendar.timezone).toBe('Asia/Shanghai')
 expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({ ...calendar, timezone: 'UTC' })
 await wrapper.setProps({ disabled: true })
 expect(wrapper.findAll('input').every(node => node.element.disabled)).toBe(true)
 expect(wrapper.findAll('textarea').every(node => node.element.disabled)).toBe(true)
 wrapper.unmount()
})
it('日历拒绝无效时区、重复星期、跨夜与冲突日期，允许补班', () => {
 expect(() => validateWorkingCalendar(calendar)).not.toThrow()
 for (const invalid of [{ timezone: 'invalid' }, { timezone: '' }, { weekdays: [1, 1] }, { start: '23:00', end: '01:00' }, { closed_dates: ['2026-02-30'] }, { closed_dates: ['0000-01-01'] }, { extra_dates: calendar.closed_dates }]) {
  expect(() => validateWorkingCalendar({ ...calendar, ...invalid })).toThrow()
 }
})
it('巡检需管理员显式点击，分页游标和未来路径检查独立受控', async () => {
 vi.mocked(approvalDiagnosticsApi.health).mockResolvedValueOnce({ checked_at: diagnostic.checked_at, scanned: 25, next_cursor: 'cursor', items: [diagnostic] }).mockResolvedValueOnce({ checked_at: diagnostic.checked_at, scanned: 1, next_cursor: null, items: [] })
 vi.mocked(approvalDiagnosticsApi.request).mockResolvedValue({ ...diagnostic, scope: 'current_and_future' })
 const { wrapper, button } = await setup()
 expect(approvalDiagnosticsApi.health).not.toHaveBeenCalled()
 await button('扫描待批申请').trigger('click'); await flushPromises()
 expect(approvalDiagnosticsApi.health).toHaveBeenCalledWith(undefined)
 expect(wrapper.text()).toContain('存在阻塞'); expect(wrapper.text()).toContain('可在异常待办修复')
 await button('检查未来路径').trigger('click'); await flushPromises()
 expect(approvalDiagnosticsApi.request).toHaveBeenCalledWith('application')
 expect(wrapper.text()).toContain('当前及未来实际路径')
 await button('扫描下一批').trigger('click'); await flushPromises()
 expect(approvalDiagnosticsApi.health).toHaveBeenLastCalledWith('cursor')
 expect(wrapper.text()).toContain('本批未发现已检查范围内的问题')
 wrapper.unmount()
 const denied = await setup(false)
 expect(denied.wrapper.find('section').exists()).toBe(false)
 denied.wrapper.unmount()
})
it('诊断失败可重试，切换申请/租户后丢弃迟到响应', async () => {
 vi.mocked(approvalDiagnosticsApi.request).mockRejectedValueOnce(new Error('network'))
 const { wrapper, tenant, button } = await setup(true, { requestId: 'application', workflowVersion: 3 })
 await button('重新诊断').trigger('click'); await flushPromises()
 expect(wrapper.text()).toContain('诊断失败，请重试')
 let resolve!: (value: ApprovalDiagnostic) => void
 vi.mocked(approvalDiagnosticsApi.request).mockReturnValueOnce(new Promise(done => { resolve = done }))
 await button('重新诊断').trigger('click')
 tenant.currentId = 'other-tenant'; resolve(diagnostic); await flushPromises()
 expect(wrapper.text()).not.toContain('存在阻塞')
 expect(wrapper.text()).not.toContain('检查时间')
 vi.mocked(approvalDiagnosticsApi.request).mockResolvedValue(diagnostic)
 await button('重新诊断').trigger('click'); await flushPromises()
 expect(wrapper.text()).toContain('存在阻塞')
 await wrapper.setProps({ requestId: 'different', workflowVersion: 1 })
 expect(wrapper.text()).not.toContain('存在阻塞')
 wrapper.unmount()
})
