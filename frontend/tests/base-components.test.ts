import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ElTable, ElPagination, type TableInstance } from 'element-plus'
import BaseTable from '../src/components/common/BaseTable.vue'
import BaseForm from '../src/components/common/BaseForm.vue'
import BaseDialog from '../src/components/common/BaseDialog.vue'
import { useSidebar } from '../src/composables/useSidebar'

describe('BaseForm', () => {
  const fields = [{ prop: 'name', label: '姓名', type: 'text' as const }]
  it('输入通过受控更新，不直接修改调用方数据', async () => {
    const original = { name: '原值' }
    const wrapper = mount(BaseForm, { props: { modelValue: original, fields } })
    await wrapper.get('input').setValue('新值')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([{ name: '新值' }])
    expect(original.name).toBe('原值')
  })
  it('校验失败显示字段错误并阻止提交；修正后可提交', async () => {
    const wrapper = mount(BaseForm, { props: { modelValue: { name: '' }, fields, rules: { name: [{ required: true, message: '请输入姓名' }] } } })
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.text()).toContain('请输入姓名'))
    expect(wrapper.emitted('submit')).toBeUndefined()
    await wrapper.setProps({ modelValue: { name: '测试用户' } })
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ name: '测试用户' }])
  })
  it('重置恢复初始快照，后续修改不污染重置值', async () => {
    const wrapper = mount(BaseForm, { props: { modelValue: { name: '初始值' }, fields } })
    await wrapper.setProps({ modelValue: { name: '修改值' } })
    await wrapper.get('button:last-child').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([{ name: '初始值' }])
  })
  it('切换记录后重置使用新记录基线，日期声明稳定传输格式', async () => {
    const wrapper = mount(BaseForm, { props: { modelValue: { name: 'A' }, fields, resetKey: 'a' } })
    await wrapper.setProps({ modelValue: { name: 'B' }, resetKey: 'b' })
    await wrapper.setProps({ modelValue: { name: 'B changed' } })
    await wrapper.get('button:last-child').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([{ name: 'B' }])
    wrapper.unmount()
    const dates = mount(BaseForm, { props: { modelValue: {}, fields: [
      { prop: 'day', label: 'Date', type: 'date' }, { prop: 'instant', label: 'Time', type: 'datetime' },
    ] } })
    expect(dates.findAllComponents({ name: 'ElDatePicker' }).map(control => control.props('valueFormat')))
      .toEqual(['YYYY-MM-DD', 'YYYY-MM-DDTHH:mm:ssZ'])
    dates.unmount()
  })
  it('加载时禁止输入、重置和键盘提交', async () => {
    const wrapper = mount(BaseForm, { props: { modelValue: { name: '值' }, fields, loading: true } })
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
  })
  it.each([
    ['number', 'ElInputNumber', 42], ['select', 'ElSelect', 'b'],
    ['multiselect', 'ElSelect', ['a', 'b']], ['date', 'ElDatePicker', '2026-10-13'],
    ['datetime', 'ElDatePicker', '2026-10-13T10:00:00'], ['switch', 'ElSwitch', true],
    ['checkbox', 'ElCheckbox', true], ['textarea', 'ElInput', '备注'],
    ['email', 'ElInput', 'name@example.com'], ['password', 'ElInput', 'fixture'],
  ] as const)('%s 字段编辑通过受控更新传给调用方', async (type, component, value) => {
    const wrapper = mount(BaseForm, { props: {
      modelValue: { field: type === 'number' ? 1 : '' },
      fields: [{ prop: 'field', label: '字段', type, options: [{ label: '选项A', value: 'a' }, { label: '选项B', value: 'b' }], checkboxLabel: '同意' }],
    } })
    const control = wrapper.getComponent({ name: component })
    control.vm.$emit('update:modelValue', value)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([{ field: value }])
    const updates = wrapper.emitted('update:modelValue')!.length
    await wrapper.setProps({ loading: true })
    expect(control.props('disabled')).not.toBe(true) // 控件继承 ElForm disabled，而非覆盖字段配置。
    await wrapper.get('button:last-child').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toHaveLength(updates)
  })
})

describe('BaseTable', () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  const row = { id: 1, name: '测试行' }
  const props = { data: [row], columns: [{ prop: 'name', label: '姓名' }], total: 21 }
  it('渲染数据和默认操作，向父组件发送正确行', async () => {
    const wrapper = mount(BaseTable, { props })
    await flushPromises()
    expect(wrapper.text()).toContain('测试行')
    const buttons = wrapper.findAll('button')
    await buttons.find(button => button.text() === '编辑')!.trigger('click')
    await buttons.find(button => button.text() === '删除')!.trigger('click')
    expect(wrapper.emitted('edit')?.[0]).toEqual([row])
    expect(wrapper.emitted('delete')?.[0]).toEqual([row])
  })
  it('支持工具栏和自定义行操作插槽', async () => {
    const wrapper = mount(BaseTable, { props: { ...props, showToolbar: true }, slots: { toolbar: '<span>批量导出</span>', actions: '<button>查看详情</button>' } })
    await flushPromises()
    expect(wrapper.text()).toContain('批量导出')
    expect(wrapper.text()).toContain('查看详情')
    expect(wrapper.text()).not.toContain('编辑')
  })
  it('显式空操作插槽不会生成默认编辑删除按钮', async () => {
    const wrapper = mount(BaseTable, { props, slots: { actions: '<template v-if="false"><button>重试</button></template>' } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('编辑')
    expect(wrapper.text()).not.toContain('删除')
    expect(wrapper.text()).not.toContain('重试')
  })
  it('空状态不显示分页，格式化列正常显示', async () => {
    const wrapper = mount(BaseTable, { props: { data: [], columns: props.columns, total: 0 } })
    expect(wrapper.text()).toContain('暂无数据')
    expect(wrapper.findComponent(ElPagination).exists()).toBe(false)
    await wrapper.setProps({ data: [row], columns: [{ ...props.columns[0], render: value => `格式：${value}` }] })
    await flushPromises()
    expect(wrapper.text()).toContain('格式：测试行')
  })
  it('分页事件和选择清空向父组件同步', async () => {
    const wrapper = mount(BaseTable, { props: { ...props, selectable: true } })
    wrapper.getComponent(ElPagination).vm.$emit('current-change', 2)
    wrapper.getComponent(ElPagination).vm.$emit('size-change', 20)
    expect(wrapper.emitted('update:currentPage')?.[0]).toEqual([2])
    expect(wrapper.emitted('update:pageSize')?.[0]).toEqual([20])
    const table = wrapper.getComponent(ElTable)
    const tableInstance = table.vm as unknown as TableInstance
    tableInstance.toggleRowSelection(row, true)
    await flushPromises()
    expect(wrapper.emitted('selection-change')?.at(-1)).toEqual([[row]])
    tableInstance.clearSelection()
    await flushPromises()
    expect(wrapper.emitted('selection-change')?.at(-1)).toEqual([[]])
  })
})

describe('BaseDialog', () => {
  it('确认、取消均正确发出事件', async () => {
    const wrapper = mount(BaseDialog, { props: { modelValue: true, title: '编辑' }, global: { stubs: { teleport: true } } })
    await flushPromises()
    const buttons = wrapper.findAll('button')
    await buttons.find(button => button.text() === '确认')!.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
    await buttons.find(button => button.text() === '取消')!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
  it('禁用或加载时禁止确认', async () => {
    const wrapper = mount(BaseDialog, { props: { modelValue: true, confirmDisabled: true }, global: { stubs: { teleport: true } } })
    await flushPromises()
    const confirm = () => wrapper.findAll('button').find(button => button.text() === '确认')!
    expect(confirm().attributes('disabled')).toBeDefined()
    await confirm().trigger('click')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    await wrapper.setProps({ confirmDisabled: false, loading: true })
    expect(confirm().attributes('disabled')).toBeDefined()
  })
  it('移动端使用视口宽度，关闭图标通知调用方', async () => {
    const sidebar = useSidebar()
    sidebar.isMobile.value = true
    const wrapper = mount(BaseDialog, { props: { modelValue: true }, global: { stubs: { teleport: true, transition: false } } })
    await flushPromises()
    expect(wrapper.find('.el-dialog').attributes('style')).toContain('calc(100vw - 24px)')
    await wrapper.get('.el-dialog__headerbtn').trigger('click')
    await wrapper.setProps({ modelValue: false })
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.emitted('close')).toHaveLength(1))
    sidebar.isMobile.value = false
  })
})
