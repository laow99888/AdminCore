import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import { createPinia } from 'pinia'
import { useAuthStore } from '../src/stores/auth'
import { useTenantStore } from '../src/stores/tenants'
import { onlineFormRelationsApi, type OnlineRelationChoices } from '../src/api/onlineFormRelations'
import RelationInput from '../src/components/onlineForms/OnlineRelationInput.vue'
import ResourcePicker from '../src/components/onlineForms/RelationResourcePicker.vue'
import FieldDesigner from '../src/components/onlineForms/FieldDesigner.vue'
import ConditionEditor from '../src/components/onlineForms/ConditionEditor.vue'
import Renderer from '../src/components/onlineForms/OnlineFormRenderer.vue'

vi.mock('../src/api/onlineFormRelations', () => ({ onlineFormRelationsApi: { choices: vi.fn(), resources: vi.fn() } }))
const wrappers: VueWrapper[] = []
const record = { id: 'ef23a35e-6dc1-4e4f-bcb0-cf69c8f21a12', title: '租户 A 供应商' }
const context = { code: 'procurement', recordId: 'record-1' }
const result = (selected: typeof record | null = record): OnlineRelationChoices => ({ selected, items: [], has_more: false })
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear()
  vi.mocked(onlineFormRelationsApi.choices).mockResolvedValue(result())
  vi.mocked(onlineFormRelationsApi.resources).mockResolvedValue([{ code: 'cg_suppliers', title: '供应商' }])
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); document.body.innerHTML = ''; localStorage.clear() })
async function harness(props: Record<string, unknown> = {}) {
  const pinia = createPinia(), auth = useAuthStore(pinia), tenants = useTenantStore(pinia)
  auth.token = 'test'; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', permissions: ['cg_suppliers:read'] }
  const wrapper = mount(RelationInput, { props: { id: 'target', label: '供应商', context, ...props }, attachTo: document.body, global: { plugins: [pinia, ElementPlus] } })
  wrappers.push(wrapper); await flushPromises(); return { wrapper, auth, tenants, pinia }
}
it('未保存字段禁止查询并解释原因', async () => {
  const { wrapper } = await harness({ context: undefined })
  expect(wrapper.text()).toContain('保存表单后可选择关联记录')
  expect(wrapper.get('input[role="combobox"]').attributes('disabled')).toBeDefined()
  expect(onlineFormRelationsApi.choices).not.toHaveBeenCalled()
})
it('只读历史通过冻结记录和明细路径解析，失权时不回显 UUID', async () => {
  const { wrapper } = await harness({ disabled: true, id: 'lines.0.target', modelValue: record.id })
  expect(onlineFormRelationsApi.choices).toHaveBeenLastCalledWith(context, 'lines.0.target', expect.objectContaining({ selected: record.id, resolve: true }), expect.any(AbortSignal))
  expect(wrapper.text()).toContain(record.title); expect(wrapper.find('input').exists()).toBe(false)
  vi.mocked(onlineFormRelationsApi.choices).mockResolvedValue(result(null))
  await wrapper.setProps({ id: 'lines.1.target' }); await flushPromises()
  expect(wrapper.text()).toContain('关联记录不可用或无权访问'); expect(wrapper.text()).not.toContain(record.id)
})
it('编辑器迟到解析刷新当前选中标题，撤权后不缓存旧摘要', async () => {
  let resolve!: (value: ReturnType<typeof result>) => void
  vi.mocked(onlineFormRelationsApi.choices).mockReturnValueOnce(new Promise(r => { resolve = r }))
  const { wrapper, tenants } = await harness({ modelValue: record.id })
  expect(wrapper.get('.el-select__placeholder').text()).toBe('关联记录不可用或无权访问')
  resolve(result()); await flushPromises()
  expect(wrapper.get('.el-select__placeholder').text()).toBe(record.title)
  vi.mocked(onlineFormRelationsApi.choices).mockResolvedValue(result(null))
  tenants.currentId = 'tenant-b'; await flushPromises()
  expect(wrapper.get('.el-select__placeholder').text()).toBe('关联记录不可用或无权访问')
  expect(wrapper.text()).not.toContain(record.title)
})
it('租户和权限变化清除摘要，旧解析响应不能恢复', async () => {
  const { wrapper, auth, tenants } = await harness({ disabled: true, modelValue: record.id })
  let resolve!: (value: ReturnType<typeof result>) => void
  vi.mocked(onlineFormRelationsApi.choices).mockReturnValueOnce(new Promise(r => { resolve = r })).mockResolvedValue(result(null))
  await wrapper.setProps({ id: 'lines.0.target' }); tenants.currentId = 'tenant-b'; auth.user = { ...auth.user!, permissions: [] }
  await flushPromises(); resolve(result()); await flushPromises()
  expect(wrapper.text()).not.toContain(record.title); expect(wrapper.text()).toContain('关联记录不可用或无权访问')
})
it('切换记录上下文和禁用状态会丢弃迟到搜索选项', async () => {
  const { wrapper } = await harness()
  let resolve!: (value: ReturnType<typeof result>) => void
  vi.mocked(onlineFormRelationsApi.choices).mockReturnValueOnce(new Promise(r => { resolve = r }))
  wrapper.getComponent(ElSelect).vm.$emit('visible-change', true); await flushPromises()
  await wrapper.setProps({ context: { code: 'procurement', recordId: 'record-2' }, disabled: true })
  resolve({ ...result(), items: [record] }); await flushPromises()
  expect(wrapper.text()).not.toContain(record.title); expect(wrapper.find('input').exists()).toBe(false)
})
it('搜索错误提供重试，远程选择只写入标识', async () => {
  const { wrapper } = await harness()
  vi.mocked(onlineFormRelationsApi.choices).mockRejectedValueOnce(new Error('网络错误')).mockResolvedValueOnce({ ...result(null), items: [record] })
  wrapper.getComponent(ElSelect).vm.$emit('visible-change', true); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('重试')
  await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises()
  const select = wrapper.getComponent(ElSelect)
  expect(select.findAllComponents({ name: 'ElOption' }).map(item => item.props('label'))).toContain(record.title)
  select.vm.$emit('update:modelValue', record.id)
  expect(wrapper.emitted('update:modelValue')).toEqual([[record.id]])
})
it('资源选择器仅展示服务端登记列表，切租户丢弃旧资源响应', async () => {
  const { pinia, tenants } = await harness()
  let resolve!: (value: { code: string; title: string }[]) => void
  vi.mocked(onlineFormRelationsApi.resources).mockReturnValueOnce(new Promise(r => { resolve = r })).mockResolvedValue([])
  const wrapper = mount(ResourcePicker, { props: { modelValue: 'cg_suppliers' }, global: { plugins: [pinia, ElementPlus] } }); wrappers.push(wrapper)
  tenants.currentId = 'tenant-b'; await flushPromises(); resolve([{ code: 'cg_suppliers', title: '失权摘要' }]); await flushPromises()
  expect(wrapper.text()).not.toContain('失权摘要')
  expect(wrapper.getComponent(ElSelect).findAllComponents({ name: 'ElOption' })[0]!.props('disabled')).toBe(true)
})
it('设计器关联资源可选且没有默认值，条件只有空和非空', async () => {
  const { pinia } = await harness()
  const fields = [{ key: 'target', label: '供应商', type: 'relation' as const, resource: 'cg_suppliers', required: false }]
  const designer = mount(FieldDesigner, { props: { modelValue: fields }, global: { plugins: [pinia, ElementPlus] } }); wrappers.push(designer); await flushPromises()
  expect(designer.find('.default-row').exists()).toBe(false); expect(designer.findComponent(ResourcePicker).exists()).toBe(true)
  const condition = mount(ConditionEditor, { props: { fields, id: 'test', modelValue: [{ field: 'target', op: 'not_empty' }] }, global: { plugins: [ElementPlus] } }); wrappers.push(condition)
  expect(condition.findAllComponents(ElSelect)[1]!.findAllComponents({ name: 'ElOption' }).map(row => row.props('value'))).toEqual(['empty', 'not_empty'])
})
it('父表单禁用状态同时覆盖主表和明细关联', async () => {
  const { pinia } = await harness()
  const wrapper = mount(Renderer, { props: { disabled: true, attachmentContext: context, modelValue: { target: record.id, lines: [{ target: record.id }] }, definition: { schema_version: 2, fields: [
    { key: 'target', label: '主供应商', type: 'relation', resource: 'cg_suppliers', required: false },
    { key: 'lines', label: '明细', type: 'detail', required: false, fields: [{ key: 'target', label: '明细供应商', type: 'relation', resource: 'cg_suppliers', required: false }] },
  ] } }, global: { plugins: [pinia, ElementPlus] } }); wrappers.push(wrapper); await flushPromises()
  expect(wrapper.findAllComponents(RelationInput)).toHaveLength(2); expect(wrapper.findAll('input')).toHaveLength(0)
  expect(onlineFormRelationsApi.choices).toHaveBeenCalledWith(context, 'lines.0.target', expect.objectContaining({ resolve: true }), expect.any(AbortSignal))
})
