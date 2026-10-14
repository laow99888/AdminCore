import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const malicious = '<script>window.printAttack=true</script><img src=x onerror="alert(1)"> javascript:alert(1) 中文\n第二行'
async function setup(page: Page, options: { english?: boolean; dark?: boolean; empty?: boolean; blocked?: boolean; delayed?: boolean; failSecondPageOnce?: boolean } = {}) {
  const access = { permissions: ['*'] }
  let failedSecondPage = false
  let release: (() => void) | undefined
  const held = new Promise<void>(resolve => { release = resolve })
  await page.addInitScript(options => {
    localStorage.setItem('token', 'isolated-print-fixture')
    localStorage.setItem('language', options.english ? 'en-US' : 'zh-CN')
    localStorage.setItem('theme', options.dark ? 'dark' : 'light')
    const original = window.open.bind(window)
    window.open = (...args: Parameters<typeof window.open>) => {
      if (options.blocked) return null
      const child = original(...args)
      if (child) child.print = () => { child.document.documentElement.dataset.printCalled = 'true' }
      return child
    }
  }, options)
  // 与正式 Nginx 保持同样的脚本约束，验证打印无需放宽 SPA 的 CSP。
  await page.route(/\/(?:logs|users)(?:\?.*)?$/, async route => {
    if (!route.request().isNavigationRequest()) return route.continue()
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': "default-src 'self'; script-src 'self'; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'" } })
  })
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    const user = { id: 'print-member', username: 'member', email: 'm@example.test', avatar: '', first_name: '', last_name: '', phone: '', bio: '',
      is_staff: true, permissions: access.permissions, profile_version: 1, has_avatar: false, avatar_enabled: false }
    if (path.endsWith('/auth/me/') || path.endsWith('/auth/profile/')) return route.fulfill({ json: envelope(user) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'l', name: '操作日志', path: '/logs', icon: 'file-text' }, { id: 's', name: '系统设置', path: '/settings', icon: 'settings' }]) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (path.endsWith('/users/')) {
      const current = Number(url.searchParams.get('page') || 1)
      return route.fulfill({ json: envelope({ items: [{ ...user, id: `user-${current}`, username: `print-user-page-${current}`, email: 'v***@example.test', is_active: true, roles: [], login_count: 0,
        first_name: malicious, last_name: '中文姓', password: 'private-password-must-not-print', phone: '138****3210', private_phone: 'private-phone-must-not-print' }], pagination: { total: 21, page: current, page_size: 10, total_pages: 3 } }) })
    }
    if (path.includes('/logs/')) {
      if (options.delayed) await held
      const current = Number(url.searchParams.get('page') || 1)
      if (options.failSecondPageOnce && current === 2 && !failedSecondPage) {
        failedSecondPage = true
        return route.fulfill({ status: 503, json: { code: 503, message: 'isolated temporary list failure', data: null } })
      }
      return route.fulfill({ json: envelope({ items: options.empty ? [] : [{ id: `row-${current}`, created_at: '2026-10-14 12:30:00', action: 'read', resource: current === 1 ? malicious : 'page-two-only', status: 200,
        description: 'private-description-must-not-print', ip_address: 'private-ip-must-not-print', request_data: { token: 'private-token-must-not-print' }, username: '成员中文', level: 'ERROR', message: 'private-stack-must-not-print' }], pagination: { total: options.empty ? 0 : 21, page: current, page_size: 10, total_pages: 3 } }) })
    }
    return route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 0 }, totals: {}, login_trend: [], task_status: {} }) })
  })
  return { release: () => release?.(), revoke: () => { access.permissions = [] } }
}
const printButton = (page: Page) => page.getByRole('button', { name: /打印 \/ 保存 PDF（当前页）|Print \/ Save PDF \(current page\)/ })
async function openPrint(page: Page) {
  const opened = page.waitForEvent('popup')
  await printButton(page).click()
  const popup = await opened
  await expect(popup.locator('html')).toHaveAttribute('data-print-called', 'true')
  return popup
}

test('当前页白名单打印，恶意文本不执行；保存 PDF 提示、中文与重复点击保护', async ({ page, context }) => {
  await setup(page)
  await page.goto('/logs')
  await expect(printButton(page)).toBeEnabled()
  const popup = await openPrint(page)
  await expect(popup.locator('tbody tr')).toHaveCount(1)
  await expect(popup.locator('tbody')).toContainText(malicious)
  await expect(popup.locator('body')).toContainText('当前第 1 页 · 1 条记录')
  await expect(popup.locator('body')).toContainText('另存为 PDF')
  await expect(popup.locator('body')).not.toContainText('private-description-must-not-print')
  await expect(popup.locator('body')).not.toContainText('private-token-must-not-print')
  await expect(popup.locator('script,img,a')).toHaveCount(0)
  expect(await popup.evaluate(() => window.opener)).toBeNull()
  expect(await popup.evaluate(() => 'printAttack' in window)).toBe(false)
  await expect(printButton(page)).toBeDisabled()
  await printButton(page).dispatchEvent('click')
  expect(context.pages()).toHaveLength(2)
  const closed = popup.waitForEvent('close')
  await popup.evaluate(() => window.dispatchEvent(new Event('afterprint')))
  await closed
  await expect(printButton(page)).toBeEnabled()
  await page.locator('.el-pager .number').filter({ hasText: /^2$/ }).click()
  await expect(page.getByText('page-two-only', { exact: true })).toBeVisible()
  const second = await openPrint(page)
  await expect(second.locator('body')).toContainText('当前第 2 页 · 1 条记录')
  await expect(second.locator('tbody')).toContainText('page-two-only')
  await expect(second.locator('tbody')).not.toContainText(malicious)
  await second.close()
  await expect(printButton(page)).toBeEnabled()
})

test('弹窗被拦截时明确提示，可重试', async ({ page }) => {
  await setup(page, { blocked: true })
  await page.goto('/logs')
  await expect(printButton(page)).toBeEnabled()
  await printButton(page).click()
  await expect(page.getByText('浏览器阻止了打印窗口，请允许弹窗后重试', { exact: true })).toBeVisible()
  await expect(printButton(page)).toBeEnabled()
})

test('当前页没有数据时不打开窗口', async ({ page, context }) => {
  await setup(page, { empty: true })
  await page.goto('/logs')
  await expect(page.locator('.table-empty')).toBeVisible()
  await expect(printButton(page)).toBeDisabled()
  await expect(page.getByText('仅打印当前第 1 页，共 0 条记录', { exact: true })).toBeVisible()
  expect(context.pages()).toHaveLength(1)
})

test('第二页请求失败时禁止把上一页数据按第二页打印，重新切页请求成功后恢复', async ({ page, context }) => {
  await setup(page, { failSecondPageOnce: true })
  await page.goto('/logs')
  await expect(printButton(page)).toBeEnabled()
  const failed = page.waitForResponse(response => response.url().includes('/logs/operation/') && new URL(response.url()).searchParams.get('page') === '2' && response.status() === 503)
  await page.locator('.el-pager .number').filter({ hasText: /^2$/ }).click()
  await failed
  await expect(page.locator('.el-pager .number.is-active')).toHaveText('2')
  await expect(printButton(page)).toBeDisabled()
  await printButton(page).dispatchEvent('click')
  expect(context.pages()).toHaveLength(1)
  await page.getByRole('listitem', { name: '第 1 页', exact: true }).click()
  await expect(printButton(page)).toBeEnabled()
  await page.locator('.el-pager .number').filter({ hasText: /^2$/ }).click()
  await expect(page.getByText('page-two-only', { exact: true })).toBeVisible()
  await expect(printButton(page)).toBeEnabled()
  const popup = await openPrint(page)
  await expect(popup.locator('body')).toContainText('当前第 2 页 · 1 条记录')
  await expect(popup.locator('tbody')).toContainText('page-two-only')
  await expect(popup.locator('tbody')).not.toContainText(malicious)
  await popup.close()
})

test('加载完成前禁止打印，页签离开关闭独立窗口，KeepAlive 恢复可再次打印', async ({ page }) => {
  const state = await setup(page, { delayed: true })
  await page.goto('/logs')
  await expect(printButton(page)).toBeDisabled()
  await expect(page.getByText('数据加载中，暂不能打印', { exact: true })).toBeVisible()
  state.release()
  await expect(printButton(page)).toBeEnabled()
  const popup = await openPrint(page)
  if (page.viewportSize()!.width <= 768) await page.getByRole('button', { name: /打开菜单|Open Menu/ }).click()
  const closed = popup.waitForEvent('close')
  await page.locator('.sidebar-menu a[href="/settings"]').click()
  await closed
  await page.locator('.navigation-tab[data-path="/logs"]').click()
  await expect(printButton(page)).toBeEnabled()
  const restored = await openPrint(page)
  await restored.close()
})

test('权限刷新撤销访问后关闭已经打开的敏感打印窗口', async ({ page }) => {
  const access = await setup(page)
  await page.goto('/logs')
  const popup = await openPrint(page)
  const closed = popup.waitForEvent('close')
  access.revoke()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await closed
  await expect(page).toHaveURL(/\/403$/)
})

test('用户列表打印明确白名单，分页后仅含脱敏联系方式且无上一页或额外私密字段', async ({ page }) => {
  await setup(page)
  await page.goto('/users')
  await expect(printButton(page)).toBeEnabled()
  await page.locator('.el-pager .number').filter({ hasText: /^2$/ }).click()
  await expect(page.getByText('print-user-page-2', { exact: true })).toBeVisible()
  const popup = await openPrint(page)
  await expect(popup.locator('thead th')).toHaveCount(6)
  await expect(popup.locator('tbody')).toContainText('v***@example.test')
  await expect(popup.locator('tbody')).toContainText('138****3210')
  await expect(popup.locator('tbody')).toContainText('print-user-page-2')
  await expect(popup.locator('tbody')).toContainText(malicious)
  await expect(popup.locator('tbody')).not.toContainText('print-user-page-1')
  await expect(popup.locator('body')).not.toContainText('private-password-must-not-print')
  await expect(popup.locator('body')).not.toContainText('private-phone-must-not-print')
  await expect(popup.locator('script,img,a')).toHaveCount(0)
  await popup.close()
})

for (const dark of [false, true]) {
  test(`375px 英文${dark ? '深色' : '浅色'}打印入口无溢出，打印文档始终白底`, async ({ page }, info) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await setup(page, { english: true, dark })
    await page.goto('/logs')
    await expect(printButton(page)).toBeEnabled()
    expect(await printButton(page).evaluate(button => button.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await printButton(page).focus()
    const opened = page.waitForEvent('popup')
    await page.keyboard.press('Enter')
    const popup = await opened
    await expect(popup.locator('body')).toContainText('Current page 1 · 1 records')
    await expect(popup.locator('body')).toContainText('Save as PDF')
    expect(await popup.locator('html').evaluate(root => getComputedStyle(root).backgroundColor)).toBe('rgb(255, 255, 255)')
    await popup.screenshot({ path: info.outputPath(`print-english-${dark ? 'dark' : 'light'}.png`), fullPage: true })
    await popup.close()
  })
}
