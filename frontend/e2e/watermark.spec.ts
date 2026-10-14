import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, options: { enabled?: boolean; dark?: boolean; english?: boolean; storageBlocked?: boolean } = {}) {
  const state = { id: 'watermark-member', username: 'watermark_member', mustChange: false, rejectIdentity: false }
  await page.addInitScript(options => {
    localStorage.setItem('token', 'isolated-watermark-fixture')
    if (options.enabled) localStorage.setItem('admincore:page-watermark', 'true')
    if (options.dark) localStorage.setItem('theme', 'dark')
    if (options.english) localStorage.setItem('language', 'en-US')
    const drawn: string[] = []
    Object.defineProperty(window, '__watermarkDrawnText', { value: drawn })
    const fillText = CanvasRenderingContext2D.prototype.fillText
    CanvasRenderingContext2D.prototype.fillText = function (text, x, y, maxWidth) {
      drawn.push(String(text))
      if (maxWidth === undefined) fillText.call(this, text, x, y)
      else fillText.call(this, text, x, y, maxWidth)
    }
    if (options.storageBlocked) {
      const set = Storage.prototype.setItem
      Storage.prototype.setItem = function (key, value) {
        if (key === 'admincore:page-watermark') throw new Error('Fixture storage unavailable')
        set.call(this, key, value)
      }
    }
  }, options)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    const user = { id: state.id, username: state.username, email: 'private@example.test', avatar: '', first_name: '', last_name: '', phone: '', bio: '',
      permissions: ['*'], profile_version: 1, has_avatar: false, avatar_enabled: false, must_change_password: state.mustChange }
    if (path.endsWith('/auth/me/')) return route.fulfill({ status: state.rejectIdentity ? 401 : 200, json: envelope(user) })
    if (path.endsWith('/auth/profile/')) return route.fulfill({ json: envelope(user) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/auth/logout/')) return route.fulfill({ json: envelope(null) })
    return route.fulfill({ json: envelope({ count: 0, results: [], totals: {}, login_trend: [], task_status: {} }) })
  })
  return state
}

const watermark = (page: Page) => page.getByTestId('page-watermark')
const switchControl = (page: Page, english = false) => page.getByRole('switch', { name: english ? 'Enable Page Watermark' : '启用页面水印', exact: true })
const switchTarget = (page: Page) => page.locator('.watermark-settings .el-switch')
async function expectPattern(page: Page) {
  await expect(watermark(page)).toBeVisible()
  await expect(page.locator('.watermark-pattern > div')).toHaveCSS('background-image', /^url\("?data:image\/png;/)
}

test('设置默认关闭，键盘启用、点击透传与持久化关闭', async ({ page }) => {
  await setup(page)
  await page.goto('/settings')
  await expect(switchControl(page)).toHaveAttribute('aria-checked', 'false')
  await expect(watermark(page)).toHaveCount(0)
  await switchControl(page).focus()
  await page.keyboard.press('Space')
  await expectPattern(page)
  await expect(watermark(page)).toHaveCSS('pointer-events', 'none')
  const drawn = await page.evaluate(() => (window as unknown as { __watermarkDrawnText: string[] }).__watermarkDrawnText)
  expect(drawn).toContain('AdminCore')
  expect(drawn).toContain('watermark_member')
  expect(drawn).not.toContain('private@example.test')
  expect(await page.evaluate(() => localStorage.getItem('admincore:page-watermark'))).toBe('true')
  await page.getByRole('button', { name: '切换到深色模式', exact: true }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await switchTarget(page).click()
  await expect(watermark(page)).toHaveCount(0)
  await page.reload()
  await expect(switchControl(page)).toHaveAttribute('aria-checked', 'false')
  await expect(watermark(page)).toHaveCount(0)
})

test('身份更换重新绘制，公共页及强制改密不带身份水印', async ({ page }) => {
  const state = await setup(page, { enabled: true })
  await page.goto('/settings')
  await expectPattern(page)
  await page.evaluate(() => { (window as unknown as { __watermarkDrawnText: string[] }).__watermarkDrawnText.length = 0 })
  state.id = 'watermark-next'; state.username = '<img onerror=alert(1)>'
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect.poll(() => page.evaluate(() => (window as unknown as { __watermarkDrawnText: string[] }).__watermarkDrawnText)).toContain(state.username)
  await expect(watermark(page).locator('img')).toHaveCount(0)
  await page.goto('/403')
  await expect(watermark(page)).toHaveCount(0)
  await page.goto('/settings')
  await expectPattern(page)
  state.mustChange = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page).toHaveURL(/\/change-password$/)
  await expect(watermark(page)).toHaveCount(0)
})

test('退出立即移除身份水印，保留无身份信息的浏览器偏好', async ({ page }) => {
  await setup(page, { enabled: true })
  await page.goto('/settings')
  await expectPattern(page)
  await page.getByRole('button', { name: '用户菜单', exact: true }).click()
  await page.getByRole('menuitem', { name: '退出登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(watermark(page)).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('admincore:page-watermark'))).toBe('true')
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
})

test('会话失效时清除水印；偏好无法保存有提示且本次仍可关闭', async ({ page }) => {
  const state = await setup(page, { storageBlocked: true })
  await page.goto('/settings')
  await switchTarget(page).click()
  await expectPattern(page)
  await expect(page.getByRole('status').filter({ hasText: '浏览器无法保存水印偏好' })).toBeVisible()
  await switchTarget(page).click()
  await expect(watermark(page)).toHaveCount(0)
  await switchTarget(page).click()
  await expectPattern(page)
  state.rejectIdentity = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(watermark(page)).toHaveCount(0)
})

test('英文深色和窄屏水印不遮挡布局或点击', async ({ page }, info) => {
  await setup(page, { enabled: true, dark: true, english: true })
  await page.goto('/settings')
  await expectPattern(page)
  await expect(switchControl(page, true)).toHaveAttribute('aria-checked', 'true')
  await expect(page.locator('html')).toHaveClass(/dark/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const box = await watermark(page).boundingBox()
  expect(box!.x).toBe(0)
  expect(box!.width).toBe(page.viewportSize()!.width)
  await switchTarget(page).scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('watermark-dark.png'), fullPage: true })
  await switchTarget(page).click()
  await expect(watermark(page)).toHaveCount(0)
})
