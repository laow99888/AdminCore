import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus, { ElTable, type TableInstance } from 'element-plus'
import request from '../src/api/request'
import GeneratedQueryWorkbench from '../src/components/codegen/GeneratedQueryWorkbench.vue'
import GeneratedBulkDelete from '../src/components/codegen/GeneratedBulkDelete.vue'
import BaseTable from '../src/components/common/BaseTable.vue'
import { emptyAdvanced, type QueryDefinition, type SavedQuery } from '../src/components/codegen/queryTypes'

vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string) => text, registerUiMessages: vi.fn() }))
vi.mock('../src/api', () => ({ newIdempotencyKey: () => 'bulk-idempotent-key' }))
vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }, errorMessage: (_error: unknown, fallback: string) => fallback }))
const wrappers: ReturnType<typeof mount>[] = []
const current = (): QueryDefinition => ({ filters: { active: 'true' }, advanced: emptyAdvanced(), ordering: '-code' })
const fields = [{ name: 'code', label: '编码', kind: 'string' as const, query: 'eq' as const }, { name: 'name', label: '名称', kind: 'string' as const, query: 'contains' as const }]
const row: SavedQuery = { id: 'saved-1', name: '常用采购', shared: false, editable: true, version: 3, available: true, definition: current() }
const Dialog = defineComponent({ props: ['modelValue', 'confirmDisabled', 'loading'], emits: ['confirm'], template: '<section v-if="modelValue"><slot /><button :disabled="confirmDisabled || loading" @click="$emit(\'confirm\')">确认测试删除</button></section>' })
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
  vi.mocked(request.get).mockResolvedValue({ data: { data: { items: [], unavailable: 0 } } })
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks() })
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(item => item.text() === text)!
function query(owner = 'account-tenant-module') {
  const wrapper = mount(GeneratedQueryWorkbench, { props: { endpoint: '/orders/records/', fields, current: current(), owner, administrator: true }, global: { plugins: [ElementPlus] } })
  wrappers.push(wrapper); return wrapper
}

it('高级条件支持受控字段和运算符，保留基础筛选并限制10项', async () => {
  const wrapper = query(); await flushPromises()
  await button(wrapper, '添加条件').trigger('click')
  await wrapper.get('.condition-row select').setValue('name')
  await wrapper.findAll('.condition-row select')[1]!.setValue('contains')
  await wrapper.get('.condition-row input').setValue('待处理')
  await button(wrapper, '应用高级条件').trigger('click')
  expect(wrapper.emitted('apply')?.at(-1)).toEqual([{ ...current(), advanced: { match: 'all', conditions: [{ field: 'name', op: 'contains', value: '待处理' }] } }])
  for (let index = 0; index < 9; index++) await button(wrapper, '添加条件').trigger('click')
  expect(wrapper.findAll('.condition-row')).toHaveLength(10)
  expect(button(wrapper, '添加条件').attributes('disabled')).toBeDefined()
  await button(wrapper, '清空高级条件').trigger('click')
  expect(wrapper.emitted('apply')?.at(-1)?.[0]).toEqual(current())
})

it('服务端保存方案，并仅持久化选择ID；新组件恢复，账号租户间隔离', async () => {
  vi.mocked(request.post).mockResolvedValue({ data: { data: row } })
  let wrapper = query(); await flushPromises()
  await wrapper.get('input[maxlength="80"]').setValue('常用采购')
  await button(wrapper, '另存为新方案').trigger('click'); await flushPromises()
  expect(request.post).toHaveBeenCalledWith('/orders/records/query-views/', { name: row.name, shared: false, definition: current() }, expect.anything())
  expect(Object.values(localStorage)).toEqual(['saved-1'])
  wrapper.unmount()
  vi.mocked(request.get).mockResolvedValue({ data: { data: { items: [row], unavailable: 0 } } })
  wrapper = query(); await flushPromises()
  expect(wrapper.emitted('apply')?.at(-1)).toEqual([current()])
  const other = query('different-account-or-tenant'); await flushPromises()
  expect(other.emitted('apply')).toBeUndefined()
})

it('失效方案不应用、允许所有者删除，且没有旧条件值', async () => {
  const key = 'admincore.query-view.v1.' + encodeURIComponent('account-tenant-module')
  localStorage.setItem(key, row.id)
  vi.mocked(request.get).mockResolvedValue({ data: { data: { items: [{ ...row, available: false, definition: { filters: {}, advanced: emptyAdvanced(), ordering: '' } }], unavailable: 1 } } })
  const wrapper = query(); await flushPromises()
  expect(wrapper.emitted('apply')).toBeUndefined()
  expect(wrapper.text()).toContain('方案已失效，未应用')
  expect(button(wrapper, '删除方案')).toBeDefined()
})

it('保存冲突保留方案草稿和旧版本，不覆盖服务端定义', async () => {
  vi.mocked(request.post).mockRejectedValue(new Error('409'))
  const wrapper = query(); await flushPromises()
  await wrapper.get('input[maxlength="80"]').setValue('保留我的修改')
  await button(wrapper, '另存为新方案').trigger('click'); await flushPromises()
  expect(wrapper.get('input[maxlength="80"]').element).toHaveProperty('value', '保留我的修改')
  expect(wrapper.get('[role="alert"]').text()).toContain('方案保存失败')
})

it('普通用户能将共享方案另存为个人方案，不能编辑原共享方案', async () => {
  vi.mocked(request.get).mockResolvedValue({ data: { data: { items: [{ ...row, shared: true, editable: false }], unavailable: 0 } } })
  vi.mocked(request.post).mockResolvedValue({ data: { data: row } })
  const wrapper = query(); await wrapper.setProps({ administrator: false }); await flushPromises()
  await wrapper.get('select').setValue(row.id)
  await wrapper.get('input[maxlength="80"]').setValue('我的副本')
  await button(wrapper, '另存为新方案').trigger('click'); await flushPromises()
  expect(request.post).toHaveBeenCalledWith('/orders/records/query-views/', expect.objectContaining({ shared: false, name: '我的副本' }), expect.anything())
})

it('加载失败提供明确重试且迟到响应在卸载后不应用', async () => {
  vi.mocked(request.get).mockRejectedValueOnce(new Error('network'))
  const wrapper = query(); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('方案加载失败')
  let resolve!: (value: unknown) => void
  vi.mocked(request.get).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  await button(wrapper, '刷新方案').trigger('click'); wrapper.unmount()
  resolve({ data: { data: { items: [row], unavailable: 0 } } }); await flushPromises()
  expect(wrapper.emitted('apply')).toBeUndefined()
})

function bulk() {
  const wrapper = mount(GeneratedBulkDelete, { props: { endpoint: '/orders/records/', selection: [{ id: 'row-1', version: 7 }] }, global: { plugins: [ElementPlus], stubs: { BaseDialog: Dialog } } })
  wrappers.push(wrapper); return wrapper
}
const preview = () => ({ data: { data: { items: [{ id: 'row-1', status: 'ready' }], ready: 1, preview_token: 'signed-preview' } } })
it('批量删除先预检，输入确认文字后携带幂等键执行，并显示逐项结果', async () => {
  vi.mocked(request.post).mockResolvedValueOnce(preview()).mockResolvedValueOnce({ data: { data: { items: [{ id: 'row-1', status: 'deleted' }], deleted: 1 } } })
  const wrapper = bulk()
  await button(wrapper, '批量删除预检').trigger('click'); await flushPromises()
  expect(request.post).toHaveBeenNthCalledWith(1, '/orders/records/bulk-preview/', { selection: [{ id: 'row-1', version: 7 }] }, expect.anything())
  expect(button(wrapper, '确认测试删除').attributes('disabled')).toBeDefined()
  await wrapper.get('input').setValue('删除选中记录')
  await button(wrapper, '确认测试删除').trigger('click'); await flushPromises()
  expect(request.post).toHaveBeenLastCalledWith('/orders/records/bulk-delete/', { preview_token: 'signed-preview', confirmation: '删除选中记录' }, expect.objectContaining({ headers: { 'Idempotency-Key': 'bulk-idempotent-key' } }))
  expect(wrapper.emitted('completed')).toHaveLength(1)
  expect(wrapper.text()).toContain('已删除 1')
  expect(button(wrapper, '确认测试删除').attributes('disabled')).toBeDefined()
})

it('跨页选择改变使预检失效，不执行旧范围', async () => {
  vi.mocked(request.post).mockResolvedValue(preview())
  const wrapper = bulk(); await button(wrapper, '批量删除预检').trigger('click'); await flushPromises()
  await wrapper.get('input').setValue('删除选中记录')
  await wrapper.setProps({ selection: [{ id: 'other-row', version: 1 }] })
  expect(button(wrapper, '确认测试删除').attributes('disabled')).toBeDefined()
  await button(wrapper, '确认测试删除').trigger('click')
  expect(request.post).toHaveBeenCalledTimes(1)
})

it('网络中断保留同一预检与幂等键以安全重试', async () => {
  vi.mocked(request.post).mockResolvedValueOnce(preview()).mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ data: { data: { items: [{ id: 'row-1', status: 'deleted' }], deleted: 1 } } })
  const wrapper = bulk(); await button(wrapper, '批量删除预检').trigger('click'); await flushPromises()
  await wrapper.get('input').setValue('删除选中记录'); await button(wrapper, '确认测试删除').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('网络中断可用相同请求重试')
  await button(wrapper, '确认测试删除').trigger('click'); await flushPromises()
  const calls = vi.mocked(request.post).mock.calls
  expect(calls[1]![1]).toEqual(calls[2]![1]); expect(calls[1]![2]).toEqual(calls[2]![2])
})

it('受控表格换页恢复明确选择，程序恢复不会产生用户选中事件', async () => {
  const first = { id: 'first', version: 1, name: 'First' }, second = { id: 'second', version: 2, name: 'Second' }
  const wrapper = mount(BaseTable, { props: { data: [first], columns: [{ prop: 'name', label: '名称' }], selectable: true, selectionIds: ['first', 'second'] } })
  wrappers.push(wrapper); await flushPromises()
  let instance = wrapper.getComponent(ElTable).vm as unknown as TableInstance
  expect(instance.getSelectionRows()).toEqual([first]); expect(wrapper.emitted('selection-change')).toBeUndefined()
  await wrapper.setProps({ data: [second] }); await flushPromises()
  instance = wrapper.getComponent(ElTable).vm as unknown as TableInstance
  expect(instance.getSelectionRows()).toEqual([second]); expect(wrapper.emitted('selection-change')).toBeUndefined()
  await wrapper.setProps({ data: [first, second], selectionIds: ['second'] }); await flushPromises()
  expect(instance.getSelectionRows()).toEqual([second])
  instance.toggleRowSelection(second, false); await flushPromises()
  expect(wrapper.emitted('selection-change')?.at(-1)).toEqual([[]])
})
