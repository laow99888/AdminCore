import { afterEach, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia } from 'pinia'
import { useThemeStore } from '../src/stores/theme'
import BaseChart from '../src/components/common/BaseChart.vue'

const mocks = vi.hoisted(() => ({ init: vi.fn(), use: vi.fn() }))
vi.mock('echarts/core', () => mocks)
vi.mock('../src/i18n/uiText', () => ({ uiText: (value: string) => value }))
afterEach(() => { vi.clearAllMocks() })

it('深浅主题切换重建图表，保留点击事件并在卸载时释放实例与事件监听', async () => {
  const charts = Array.from({ length: 2 },() => ({ dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn(), on: vi.fn<(name: string, callback: (data: unknown) => void) => void>() }))
  mocks.init.mockReturnValueOnce(charts[0]).mockReturnValueOnce(charts[1])
  const pinia = createPinia(), theme = useThemeStore(pinia)
  const wrapper = mount(BaseChart,{ props: { option: { series: [] },caption: '采购趋势' }, global: { plugins: [pinia] } })
  expect(mocks.init).toHaveBeenNthCalledWith(1,expect.any(HTMLElement),undefined)
  expect(charts[0].setOption).toHaveBeenCalledWith(expect.objectContaining({ backgroundColor: 'transparent' }),true)
  charts[0].on.mock.calls[0][1]({ dataIndex: 1 }); expect(wrapper.emitted('select')).toEqual([[1]])
  theme.isDark = true; await nextTick()
  expect(charts[0].dispose).toHaveBeenCalledOnce()
  expect(mocks.init).toHaveBeenNthCalledWith(2,expect.any(HTMLElement),'dark')
  charts[1].on.mock.calls[0][1]({ dataIndex: 2 }); expect(wrapper.emitted('select')).toEqual([[1],[2]])
  window.dispatchEvent(new Event('resize')); expect(charts[1].resize).toHaveBeenCalledOnce()
  wrapper.unmount(); expect(charts[1].dispose).toHaveBeenCalledOnce()
  window.dispatchEvent(new Event('resize')); expect(charts[1].resize).toHaveBeenCalledOnce()
})
