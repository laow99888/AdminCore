import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import BaseVirtualTable from '../src/components/common/BaseVirtualTable.vue'
import { useTablePreferencesStore } from '../src/stores/tablePreferences'

const scroll = vi.fn(), reset = vi.fn(), disconnect = vi.fn()
let resized: ResizeObserverCallback
const stub = defineComponent({ name: 'ElTableV2', props: ['columns', 'data', 'width', 'height', 'rowHeight', 'cache', 'rowKey'], setup(_props, { expose }) {
  expose({ scrollToTop: scroll, scrollTo: reset })
  return () => h('div', { class: 'virtual-stub' })
} })
const rows = () => Array.from({ length: 100 }, (_, index) => ({ id: `row-${index}`, name: `name-${index}` }))
const columns = [{ prop: 'name', label: '姓名', width: '180px' }]
function create(props: Record<string, unknown> = {}, actions = false) {
  const wrapper = mount(BaseVirtualTable, { props: { data: rows(), columns, label: '虚拟列表', ...props },
    slots: actions ? { actions: '<button>action</button>' } : {}, global: { stubs: { ElTableV2: stub } } })
  resized([{ contentRect: { width: 375 } } as ResizeObserverEntry], {} as ResizeObserver)
  return wrapper
}

describe('虚拟表格受限输入、键盘和生命周期', () => {
  beforeEach(() => {
    localStorage.clear(); setActivePinia(createPinia()); vi.clearAllMocks()
    vi.stubGlobal('ResizeObserver', class { constructor(callback: ResizeObserverCallback) { resized = callback } observe() {} disconnect = disconnect })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('构造有界列/行号和可选操作槽，尺寸/密度应用到虚拟化引擎', async () => {
    const wrapper = create({}, true); await nextTick()
    const table = wrapper.getComponent(stub)
    expect(table.props('columns').map((column: { key: string }) => column.key)).toEqual(['__index', 'name', '__actions'])
    expect(table.props('cache')).toBe(2); expect(table.props('width')).toBe(375); expect(table.props('rowHeight')).toBe(56)
    useTablePreferencesStore().setDensity('compact'); await flushPromises()
    expect(table.props('rowHeight')).toBe(44); expect(reset).toHaveBeenCalled()
    wrapper.unmount(); expect(disconnect).toHaveBeenCalled()
  })

  it('只在区域自身聚焦时消费键盘，Home/End/Page和边界受限', async () => {
    const wrapper = create(); await nextTick()
    const viewport = wrapper.get('[role="region"]')
    await viewport.trigger('keydown', { key: 'End' }); expect(scroll).toHaveBeenLastCalledWith(5224)
    await viewport.trigger('keydown', { key: 'ArrowDown' }); expect(scroll).toHaveBeenLastCalledWith(5224)
    await viewport.trigger('keydown', { key: 'Home' }); expect(scroll).toHaveBeenLastCalledWith(0)
    await viewport.trigger('keydown', { key: 'ArrowUp' }); expect(scroll).toHaveBeenLastCalledWith(0)
    await viewport.trigger('keydown', { key: 'PageDown' }); expect(scroll).toHaveBeenLastCalledWith(376)
    const before = scroll.mock.calls.length
    await viewport.trigger('keydown', { key: 'End', ctrlKey: true }); await viewport.trigger('keydown', { key: 'Tab' })
    expect(scroll).toHaveBeenCalledTimes(before)
  })

  it.each([
    [{ id: 'duplicate', name: 'a' }, { id: 'duplicate', name: 'b' }],
    [{ id: 1, name: 'numeric' }, { id: '1', name: 'string' }],
    [{ id: '', name: 'a' }], [{ name: 'missing' }], [{ id: Infinity }],
    Array.from({ length: 10001 }, (_, id) => ({ id })),
  ].map(data => ({ data })))('非法或过量行拒绝虚拟渲染', async ({ data }) => {
    const wrapper = create({ data }); await nextTick()
    expect(wrapper.get('[role="alert"]').text()).toContain('请使用普通表格')
    expect(wrapper.findComponent(stub).exists()).toBe(false)
  })

  it.each([[], [{ prop: '__actions', label: 'reserved' }], [{ prop: 'name', label: 'a' }, { prop: 'name', label: 'b' }]].map(value => ({ value })))('无效列拒绝', async ({ value }) => {
    const wrapper = create({ columns: value }); await nextTick()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  })

  it('加载时不向渲染器传旧行，数据上下文变化清滚动且不触发网络事件', async () => {
    const wrapper = create(); await nextTick()
    await wrapper.setProps({ loading: true })
    expect(wrapper.getComponent(stub).props('data')).toEqual([])
    await wrapper.setProps({ loading: false, data: rows().slice(0, 3), contextKey: 'new-owner' }); await flushPromises()
    expect(wrapper.getComponent(stub).props('data')).toHaveLength(3)
    expect(reset).toHaveBeenCalledWith({ scrollTop: 0, scrollLeft: 0 })
    expect(wrapper.emitted()).toEqual({})
  })
})
