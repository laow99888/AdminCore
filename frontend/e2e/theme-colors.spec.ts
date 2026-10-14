import { expect, test, type Page } from '@playwright/test'
import { colorContrast } from '../src/utils/themeColors'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, options: { english?: boolean; dark?: boolean; invalid?: boolean; blocked?: boolean } = {}) {
  await page.addInitScript(options => {
    localStorage.setItem('token', 'isolated-theme-fixture')
    localStorage.setItem('language', options.english ? 'en-US' : 'zh-CN')
    localStorage.setItem('theme', options.dark ? 'dark' : 'light')
    if (options.invalid && localStorage.getItem('admincore:theme-color') === null) localStorage.setItem('admincore:theme-color', 'url(javascript:bad)')
    if (options.blocked) {
      const original = Storage.prototype.setItem
      Storage.prototype.setItem = function (key, value) {
        if (key === 'admincore:theme-color') throw new DOMException('fixture blocked', 'SecurityError')
        original.call(this, key, value)
      }
    }
  }, options)
  const user = { id: 'theme-member', username: 'theme_member', email: 'fixture@example.test', first_name: '', last_name: '', phone: '', bio: '',
    permissions: ['*'], profile_version: 1, has_avatar: false, avatar_enabled: false }
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/') || path.endsWith('/auth/profile/')) return route.fulfill({ json: envelope(user) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    return route.fulfill({ json: envelope({ count: 0, results: [], totals: {}, login_trend: [], task_status: {} }) })
  })
}

const field = (page: Page, english = false) => page.getByRole('textbox', { name: english ? 'Theme Color Hex Value' : '主题颜色十六进制值', exact: true })
const apply = (page: Page, english = false) => page.getByRole('button', { name: english ? 'Apply Theme Color' : '应用主题颜色', exact: true })
function hex(rgb: string) {
  const components = rgb.match(/[\d.]+/g)!.slice(0, 3).map(Number)
  return '#' + components.map(value => Math.round(value).toString(16).padStart(2, '0')).join('')
}
async function actualContrasts(page: Page, english: boolean) {
  const button = apply(page, english)
  await button.scrollIntoViewIfNeeded()
  await page.mouse.move(0, 0)
  await expect.poll(async () => {
    const [foreground, background] = await button.evaluate(element => { const css = getComputedStyle(element); return [css.color, css.backgroundColor] })
    return colorContrast(hex(foreground!), hex(background!))
  }).toBeGreaterThanOrEqual(4.5)
  await button.hover()
  await expect.poll(async () => {
    const [foreground, background] = await button.evaluate(element => { const css = getComputedStyle(element); return [css.color, css.backgroundColor] })
    return colorContrast(hex(foreground!), hex(background!))
  }).toBeGreaterThanOrEqual(4.5)
  const actual = await page.locator('.theme-color-settings').evaluate(element => {
    const root = getComputedStyle(document.documentElement)
    const card = element.closest('.base-card')!
    return { primary: root.getPropertyValue('--el-color-primary').trim(), subtle: root.getPropertyValue('--admincore-primary-subtle').trim(),
      card: getComputedStyle(card).backgroundColor, palette: [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map(step => root.getPropertyValue(`--color-primary-${step}`).trim()) }
  })
  expect(colorContrast(actual.primary, hex(actual.card))).toBeGreaterThanOrEqual(4.5)
  expect(colorContrast(actual.primary, actual.subtle)).toBeGreaterThanOrEqual(4.5)
  expect(actual.palette.every(color => /^#[A-F\d]{6}$/.test(color))).toBe(true)
}

test('真实设置入口草稿校验、应用、明暗完整换色和刷新后恢复默认', async ({ page }) => {
  await setup(page)
  await page.goto('/settings')
  await expect(page.locator('html')).not.toHaveAttribute('data-custom-theme-color')
  await field(page).fill('#XYZXYZ')
  await apply(page).click()
  await expect(page.getByRole('alert').filter({ hasText: '#RRGGBB' })).toBeVisible()
  await expect(page.locator('html')).not.toHaveAttribute('data-custom-theme-color')
  await field(page).fill('#2563EB')
  expect(await page.evaluate(() => localStorage.getItem('admincore:theme-color'))).toBeNull()
  await field(page).press('Enter')
  await expect(page.locator('html')).toHaveAttribute('data-custom-theme-color', 'true')
  await actualContrasts(page, false)
  const before = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--el-color-primary'))
  await page.getByRole('button', { name: '切换到深色模式', exact: true }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--el-color-primary'))).not.toBe(before)
  await actualContrasts(page, false)
  await page.reload()
  await expect(field(page)).toHaveValue('#2563EB')
  await page.getByRole('button', { name: '恢复默认主色', exact: true }).click()
  await expect(page.locator('html')).not.toHaveAttribute('data-custom-theme-color')
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--color-primary-500').trim())).toBe('#14b8a6')
  await page.reload()
  await expect(page.locator('html')).not.toHaveAttribute('data-custom-theme-color')
})

test('非法存储回退默认；保存失败本次仍可应用并告知刷新限制', async ({ page }) => {
  await setup(page, { invalid: true, blocked: true })
  await page.goto('/settings')
  await expect(page.locator('html')).not.toHaveAttribute('data-custom-theme-color')
  await field(page).fill('#FFFFFF')
  await apply(page).click()
  await expect(page.getByRole('status').filter({ hasText: '浏览器无法保存主题偏好' })).toBeVisible()
  await actualContrasts(page, false)
  await page.reload()
  await expect(page.locator('html')).not.toHaveAttribute('data-custom-theme-color')
})

for (const english of [false, true]) for (const dark of [false, true]) {
  test(`375px ${english ? '英文' : '中文'}${dark ? '深色' : '浅色'}极端颜色映射与控件可访问性`, async ({ page }, info) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await setup(page, { english, dark })
    await page.goto('/settings')
    await field(page, english).fill(dark ? '#000000' : '#FFFFFF')
    await field(page, english).press('Enter')
    await actualContrasts(page, english)
    await expect(page.getByRole('status').filter({ hasText: english ? 'Applied color in this mode:' : '当前模式实际主色：' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const controls = await page.locator('.theme-color-controls input[type="color"], .theme-color-controls .el-input__wrapper, .theme-color-controls button').evaluateAll(elements => elements.map(element => ({ width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height })))
    expect(controls.every(control => control.width >= 44 && control.height >= 44)).toBe(true)
    await page.screenshot({ path: info.outputPath(`theme-${english ? 'en' : 'zh'}-${dark ? 'dark' : 'light'}.png`), fullPage: true })
  })
}
