import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { ElButton, ElInput } from 'element-plus'
import { useThemeStore, THEME_COLOR_KEY } from '../src/stores/theme'
import ThemeColorSettings from '../src/components/settings/ThemeColorSettings.vue'
import { colorContrast, createThemePalette, normalizeThemeColor, PRIMARY_STEPS } from '../src/utils/themeColors'

describe('主题换色与偏好', () => {
  beforeEach(() => { localStorage.clear(); document.documentElement.removeAttribute('style'); document.documentElement.classList.remove('dark'); setActivePinia(createPinia()) })
  afterEach(() => vi.restoreAllMocks())

  it('默认不覆盖历史 Teal，完整验证后保存种子色并刷新恢复', () => {
    const theme = useThemeStore()
    expect(theme.primaryColor).toBeNull()
    expect(document.documentElement.style.getPropertyValue('--color-primary-500')).toBe('')
    expect(theme.setPrimaryColor('#2563eb')).toBe(true)
    expect(localStorage.getItem(THEME_COLOR_KEY)).toBe('#2563EB')
    expect(localStorage.length).toBe(1)
    for (const step of PRIMARY_STEPS) expect(document.documentElement.style.getPropertyValue(`--color-primary-${step}`)).toMatch(/^#[A-F\d]{6}$/)
    theme.$dispose(); setActivePinia(createPinia())
    expect(useThemeStore().primaryColor).toBe('#2563EB')
  })

  it.each(['#fff', '#12345678', '#GGGGGG', 'red', ' #2563EB', '<script>', 'null', '{"color":"#2563EB"}'])('非法输入/存储 %s 不修改主题或应用代码', value => {
    localStorage.setItem(THEME_COLOR_KEY, value)
    const theme = useThemeStore()
    expect(theme.primaryColor).toBeNull()
    expect(normalizeThemeColor(value)).toBeNull()
    theme.setPrimaryColor('#2563EB')
    expect(theme.setPrimaryColor(value)).toBe(false)
    expect(theme.primaryColor).toBe('#2563EB')
    expect(localStorage.getItem(THEME_COLOR_KEY)).toBe('#2563EB')
  })

  it('切换明暗时主色、hover、active及浅底均同步；恢复默认移除所有覆盖', () => {
    const theme = useThemeStore()
    theme.setPrimaryColor('#2563EB')
    const root = document.documentElement
    const light = root.style.getPropertyValue('--el-color-primary')
    theme.toggleTheme()
    expect(theme.isDark).toBe(true)
    expect(root.classList.contains('dark')).toBe(true)
    expect(root.style.getPropertyValue('--el-color-primary')).not.toBe(light)
    expect(root.style.getPropertyValue('--admincore-primary-on-color')).toBe('#000000')
    expect(root.style.getPropertyValue('--el-color-primary-light-9')).toBe(createThemePalette('#2563EB', true).subtle)
    theme.resetPrimaryColor()
    expect(theme.primaryColor).toBeNull()
    expect(localStorage.getItem(THEME_COLOR_KEY)).toBeNull()
    expect(root.style.length).toBe(0)
    expect(root.hasAttribute('data-custom-theme-color')).toBe(false)
    expect(root.classList.contains('dark')).toBe(true)
  })

  it('读取失败安全回退，保存/恢复失败保留当前选择并提示；可恢复后解除提示', () => {
    const read = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    const theme = useThemeStore()
    expect(theme.primaryColor).toBeNull()
    expect(theme.persistenceAvailable).toBe(false)
    read.mockRestore()
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    theme.setPrimaryColor('#000000')
    expect(theme.primaryColor).toBe('#000000')
    expect(theme.persistenceAvailable).toBe(false)
    expect(document.documentElement.hasAttribute('data-custom-theme-color')).toBe(true)
    theme.toggleTheme()
    expect(theme.isDark).toBe(true)
    write.mockRestore()
    theme.setPrimaryColor('#2563EB')
    expect(theme.persistenceAvailable).toBe(false)
    theme.toggleTheme()
    expect(theme.persistenceAvailable).toBe(true)
    const remove = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked') })
    theme.resetPrimaryColor()
    expect(theme.primaryColor).toBeNull()
    expect(theme.persistenceAvailable).toBe(false)
    remove.mockRestore()
  })

  it('store 卸载停止 watcher，不添加 window/document 全局监听器', () => {
    const windowListener = vi.spyOn(window, 'addEventListener')
    const documentListener = vi.spyOn(document, 'addEventListener')
    const theme = useThemeStore()
    theme.setPrimaryColor('#2563EB')
    const before = document.documentElement.style.cssText
    theme.$dispose(); theme.isDark = true; theme.primaryColor = '#FFFFFF'
    expect(document.documentElement.style.cssText).toBe(before)
    expect(windowListener).not.toHaveBeenCalled()
    expect(documentListener).not.toHaveBeenCalled()
  })

  it('取色/文字编辑只是草稿；非法值提示，Apply及恢复默认均可通过键盘操作', async () => {
    const theme = useThemeStore()
    const wrapper = mount(ThemeColorSettings, { global: { components: { ElButton, ElInput } } })
    const input = wrapper.get('[aria-label="主题颜色十六进制值"]')
    await input.setValue('#2563EB')
    expect(theme.primaryColor).toBeNull()
    await input.trigger('keyup', { key: 'Enter' })
    expect(theme.primaryColor).toBe('#2563EB')
    await input.setValue('#XYZXYZ')
    await input.trigger('keyup', { key: 'Enter' })
    expect(wrapper.get('[role="alert"]').text()).toContain('#RRGGBB')
    expect(theme.primaryColor).toBe('#2563EB')
    await wrapper.findAll('button').find(button => button.text() === '恢复默认主色')!.trigger('click')
    expect(theme.primaryColor).toBeNull()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})

describe('自定义色实测对比度', () => {
  it('WCAG 标准黑白及同色比值无舍入放行', () => {
    expect(colorContrast('#000000', '#FFFFFF')).toBe(21)
    expect(colorContrast('#2563EB', '#2563EB')).toBe(1)
  })
  it.each([false, true])('明暗模式 %s 下 216 个颜色样本及极端输入：按钮两端、hover/active及重要文字最低 4.5:1', dark => {
    const values = [0, 51, 102, 153, 204, 255]
    for (const red of values) for (const green of values) for (const blue of values) {
      const seed = '#' + [red, green, blue].map(value => value.toString(16).padStart(2, '0')).join('')
      const result = createThemePalette(seed, dark)
      for (const background of [result.primary, result.palette[600]!, result.palette[700]!, result.hover, result.active]) {
        expect(colorContrast(result.onColor, background), `${seed} button ${background}`).toBeGreaterThanOrEqual(4.5)
      }
      for (const background of dark ? ['#1E293B', '#0F172A', '#020617', result.subtle] : ['#FFFFFF', '#F9FAFB', '#F3F4F6', result.subtle]) {
        expect(colorContrast(result.primary, background), `${seed} text ${background}`).toBeGreaterThanOrEqual(4.5)
      }
      expect(Object.keys(result.palette)).toHaveLength(11)
    }
  })
})
