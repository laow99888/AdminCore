import { test, expect, type Page } from '@playwright/test'
import { colorContrast } from '../src/utils/themeColors'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, signedIn: boolean, dark: boolean) {
  await page.addInitScript(({ signedIn, dark }) => {
    localStorage.clear(); sessionStorage.clear()
    if (signedIn) localStorage.setItem('token', 'isolated-layout-fixture')
    localStorage.setItem('theme', dark ? 'dark' : 'light')
    localStorage.setItem('language', 'zh-CN')
  }, { signedIn, dark })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'layout-member', username: 'layout', permissions: ['*'], must_change_password: false }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([
      { id: 'layout-home', name: '仪表盘', path: '/', icon: 'layout-dashboard', children: [] },
    ]) })
    if (path.endsWith('/organization/my-tenants/')) return route.fulfill({ json: envelope([]) })
    return route.fulfill({ json: envelope({ enabled: false, required: false, count: 0, totals: {}, login_trend: [], task_status: {} }) })
  })
}

function hex(rgb: string) {
  return '#' + rgb.match(/[\d.]+/g)!.slice(0, 3).map(value => Math.round(Number(value)).toString(16).padStart(2, '0')).join('')
}

for (const dark of [false, true]) {
  test(`登录页居中与短屏可滚动 ${dark ? 'dark' : 'light'}`, async ({ page }, info) => {
    await setup(page, false, dark)
    for (const [width, height] of [[1440, 900], [375, 667], [667, 375]]) {
      await page.setViewportSize({ width: width!, height: height! })
      await page.goto('/login')
      await expect(page.getByRole('textbox', { name: '用户名', exact: true })).toBeVisible()
      const box = await page.locator('.login-card').boundingBox()
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.x + box!.width).toBeLessThanOrEqual(width! + 1)
      if (box!.height < height! - 64) expect(Math.abs(box!.y + box!.height / 2 - height! / 2)).toBeLessThan(2)
      await page.getByRole('button', { name: '登录', exact: true }).scrollIntoViewIfNeeded()
      await expect(page.getByRole('button', { name: '登录', exact: true })).toBeInViewport()
      const button = page.getByRole('button', { name: '登录', exact: true })
      const colors = await button.evaluate(element => ({ color: getComputedStyle(element).color, background: getComputedStyle(element).backgroundColor }))
      expect(colorContrast(hex(colors.color), hex(colors.background))).toBeGreaterThanOrEqual(4.5)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({ path: info.outputPath(`login-${width}-${height}.png`), fullPage: true })
    }
  })

  test(`中屏顶栏与折叠侧栏 ${dark ? 'dark' : 'light'}`, async ({ page }, info) => {
    await setup(page, true, dark)
    for (const width of [960, 1024, 1200]) {
      await page.setViewportSize({ width, height: 800 })
      await page.goto('/')
      await expect(page.locator('.app-header')).toBeVisible()
      const left = await page.locator('.header-left').boundingBox()
      const right = await page.locator('.header-right').boundingBox()
      expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x + 1)
      expect(right!.x + right!.width).toBeLessThanOrEqual(width + 1)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({ path: info.outputPath(`app-${width}.png`), fullPage: true })
    }
    await page.getByRole('button', { name: '收起侧栏', exact: true }).click()
    const link = page.locator('.sidebar-menu .menu-item').first()
    const name = await link.getAttribute('aria-label')
    expect(name).toBeTruthy()
    await link.locator('.menu-icon').hover()
    await expect(page.getByRole('tooltip').filter({ hasText: name! })).toBeVisible()
    const colors = await link.evaluate(element => ({ color: getComputedStyle(element).color, background: getComputedStyle(element.closest('aside')!).backgroundColor }))
    expect(colorContrast(hex(colors.color), hex(colors.background))).toBeGreaterThanOrEqual(4.5)
  })
}
