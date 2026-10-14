import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ElTable, type TableInstance } from 'element-plus'
import { TABLE_DENSITY_KEY, useTablePreferencesStore } from '../src/stores/tablePreferences'
import TableDensitySettings from '../src/components/settings/TableDensitySettings.vue'
import BaseTable from '../src/components/common/BaseTable.vue'

beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
afterEach(() => vi.restoreAllMocks())

describe('表格密度偏好', () => {
  it.each([null, '', 'invalid', 'large', '{"density":"compact"}'])('未保存或非法值 %s 回退舒适默认', value => {
    if (value !== null) localStorage.setItem(TABLE_DENSITY_KEY, value)
    expect(useTablePreferencesStore().density).toBe('comfortable')
  })

  it('设置入口更改共享状态并在新应用实例恢复，保持其他存储项', async () => {
    localStorage.setItem('unrelated-fixture', 'keep')
    const wrapper = mount(TableDensitySettings)
    expect(wrapper.get('input[value="comfortable"]').element).toHaveProperty('checked', true)
    await wrapper.get('input[value="compact"]').setValue(true)
    expect(useTablePreferencesStore().density).toBe('compact')
    expect(localStorage.getItem(TABLE_DENSITY_KEY)).toBe('compact')
    setActivePinia(createPinia())
    expect(useTablePreferencesStore().density).toBe('compact')
    expect(localStorage.getItem('unrelated-fixture')).toBe('keep')
  })

  it('读取存储失败安全回退，保存失败仍生效并显示提示，后续可恢复保存', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Blocked', 'SecurityError') })
    const store = useTablePreferencesStore()
    expect(store.density).toBe('comfortable')
    expect(store.persistenceUnavailable).toBe(true)
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError') })
    const wrapper = mount(TableDensitySettings)
    await wrapper.get('input[value="compact"]').setValue(true)
    expect(store.density).toBe('compact')
    expect(wrapper.get('[role="status"]').text()).toContain('本次页面内仍可使用')
    write.mockRestore()
    await wrapper.get('input[value="comfortable"]').setValue(true)
    expect(store.persistenceUnavailable).toBe(false)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('运行时拒绝非法设置值，不覆盖有效偏好', () => {
    const store = useTablePreferencesStore()
    store.setDensity('compact')
    store.setDensity('unsafe' as 'compact')
    expect(store.density).toBe('compact')
    expect(localStorage.getItem(TABLE_DENSITY_KEY)).toBe('compact')
  })

  it('切换立即作用于已挂载表格，保留实例、选择及分页且不触发查询事件', async () => {
    const row = { id: 1, name: '保留行' }
    const wrapper = mount(BaseTable, { props: { data: [row], columns: [{ prop: 'name', label: '姓名' }], selectable: true, total: 40, currentPage: 3 } })
    await flushPromises()
    const table = wrapper.getComponent(ElTable)
    const instance = table.vm as unknown as TableInstance
    instance.toggleRowSelection(row, true)
    await flushPromises()
    const beforeSelectionEvents = wrapper.emitted('selection-change')?.length
    useTablePreferencesStore().setDensity('compact')
    await flushPromises()
    expect(wrapper.attributes('data-table-density')).toBe('compact')
    expect(table.classes()).toContain('el-table--small')
    expect(wrapper.getComponent(ElTable).element).toBe(table.element)
    expect(instance.getSelectionRows()).toEqual([row])
    expect(wrapper.emitted('selection-change')?.length).toBe(beforeSelectionEvents)
    expect(wrapper.emitted('update:currentPage')).toBeUndefined()
    expect(wrapper.emitted('update:pageSize')).toBeUndefined()
    expect(wrapper.props('currentPage')).toBe(3)
    useTablePreferencesStore().setDensity('comfortable')
    await flushPromises()
    expect(table.classes()).toContain('el-table--default')
  })

  it.each(['small', 'default', 'large'] as const)('调用方显式 size=%s 在切换密度后仍生效', async size => {
    const wrapper = mount(BaseTable, { props: { data: [], columns: [], size } })
    useTablePreferencesStore().setDensity('compact')
    await flushPromises()
    expect(wrapper.getComponent(ElTable).classes()).toContain(`el-table--${size}`)
    expect(wrapper.classes()).toContain(size === 'small' ? 'density-compact' : 'density-comfortable')
    expect(wrapper.classes()).not.toContain(size === 'small' ? 'density-comfortable' : 'density-compact')
  })
})
