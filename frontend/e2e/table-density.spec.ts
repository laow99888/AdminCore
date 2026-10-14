import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, options: { english?: boolean; dark?: boolean; invalid?: boolean; blocked?: boolean } = {}) {
  await page.addInitScript(options => {
    localStorage.setItem('token', 'isolated-density-fixture')
    if (options.english) localStorage.setItem('language', 'en-US')
    localStorage.setItem('theme', options.dark ? 'dark' : 'light')
    if (options.invalid && localStorage.getItem('admincore.table-density') === null) localStorage.setItem('admincore.table-density', 'invalid')
    if (options.blocked) {
      const write = Storage.prototype.setItem
      Storage.prototype.setItem = function (key, value) {
        if (key === 'admincore.table-density') throw new DOMException('Blocked fixture', 'SecurityError')
        return write.call(this, key, value)
      }
    }
  }, options)
  const requests: string[] = []
  const user = { id: 'density-admin', username: 'admin', email: 'admin@example.com', is_staff: true, permissions: ['*'],
    first_name: '', last_name: '', phone: '', bio: '', profile_version: 1, has_avatar: false, avatar_enabled: false }
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    if (path.endsWith('/auth/me/') || path.endsWith('/auth/profile/')) return route.fulfill({ json: envelope(user) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'u', name: '用户管理', path: '/users', icon: 'users' }, { id: 's', name: '系统设置', path: '/settings', icon: 'settings' }]) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (path.endsWith('/users/')) {
      requests.push(url.search)
      const current = Number(url.searchParams.get('page') || 1)
      return route.fulfill({ json: envelope({ items: [{ ...user, id: 'row-1', username: `density-page-${current}`, is_active: true, roles: [], login_count: 0 }], pagination: { total: 41, page: current, page_size: 10, total_pages: 5 } }) })
    }
    return route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 1 }, totals: {}, login_trend: [], task_status: {} }) })
  })
  return requests
}

async function openSidebar(page: Page, path: string) {
  if (page.viewportSize()!.width <= 768) await page.getByRole('button', { name: /打开菜单|Open Menu/ }).click()
  await page.locator(`.sidebar-menu a[href="${path}"]`).click()
  await expect(page).toHaveURL(new RegExp(`${path}$`))
}

test('真实设置入口切换密度；列表即时生效、查询保留，刷新后恢复偏好', async ({ page }) => {
  const requests = await setup(page)
  await page.goto('/users')
  const table = page.locator('.base-table')
  await expect(table).toHaveAttribute('data-table-density', 'comfortable')
  const comfortablePadding = await table.locator('.el-table__body td').first().evaluate(cell => getComputedStyle(cell).paddingTop)
  const filter = page.getByPlaceholder('搜索用户名 / 邮箱')
  await filter.fill('density')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.locator('.el-pager .number').filter({ hasText: /^3$/ }).click()
  await expect(page.getByText('density-page-3', { exact: true })).toBeVisible()
  await openSidebar(page, '/settings')
  const compact = page.getByRole('radio', { name: '紧凑', exact: true })
  await compact.check()
  await expect(compact).toBeChecked()
  expect(await page.evaluate(() => localStorage.getItem('admincore.table-density'))).toBe('compact')
  await page.locator('.navigation-tab[data-path="/users"]').click()
  await expect(table).toHaveAttribute('data-table-density', 'compact')
  await expect(filter).toHaveValue('density')
  await expect(page.getByText('density-page-3', { exact: true })).toBeVisible()
  const compactPadding = await table.locator('.el-table__body td').first().evaluate(cell => getComputedStyle(cell).paddingTop)
  expect(parseFloat(compactPadding)).toBeLessThan(parseFloat(comfortablePadding))
  expect(requests.some(query => query.includes('search=density') && query.includes('page=3'))).toBe(true)
  if (page.viewportSize()!.width <= 768) {
    const buttons = await table.locator('.action-buttons button').evaluateAll(buttons => buttons.map(button => button.getBoundingClientRect().height))
    expect(buttons.length).toBeGreaterThan(0)
    expect(buttons.every(height => height >= 44)).toBe(true)
  }
  await page.reload()
  await expect(table).toHaveAttribute('data-table-density', 'compact')
  await openSidebar(page, '/settings')
  await expect(compact).toBeChecked()
  await page.getByRole('radio', { name: '舒适', exact: true }).check()
  await page.locator('.navigation-tab[data-path="/users"]').click()
  await expect(table).toHaveAttribute('data-table-density', 'comfortable')
})

test('非法偏好回退默认，保存被浏览器拒绝时仍可在当前页面切换', async ({ page }) => {
  await setup(page, { invalid: true, blocked: true })
  await page.goto('/settings')
  await expect(page.getByRole('radio', { name: '舒适', exact: true })).toBeChecked()
  await page.getByRole('radio', { name: '紧凑', exact: true }).check()
  await expect(page.getByRole('status').filter({ hasText: '本次页面内仍可使用' })).toBeVisible()
  await openSidebar(page, '/users')
  await expect(page.locator('.base-table')).toHaveAttribute('data-table-density', 'compact')
  await page.reload()
  await expect(page.locator('.base-table')).toHaveAttribute('data-table-density', 'comfortable')
})

for (const dark of [false, true]) {
  test(`375px 英文${dark ? '深色' : '浅色'}键盘切换无溢出，触摸目标保留`, async ({ page }, info) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await setup(page, { english: true, dark })
    await page.goto('/settings')
    const comfortable = page.getByRole('radio', { name: 'Comfortable', exact: true })
    await expect(comfortable).toBeChecked()
    await comfortable.focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('radio', { name: 'Compact', exact: true })).toBeChecked()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const sizes = await page.locator('.density-options label').evaluateAll(labels => labels.map(label => ({ width: label.getBoundingClientRect().width, height: label.getBoundingClientRect().height })))
    expect(sizes.every(size => size.width >= 44 && size.height >= 44)).toBe(true)
    await expect(page.locator('html')).toHaveClass(dark ? /dark/ : /^(?!.*dark).*$/)
    await page.screenshot({ path: info.outputPath(`density-settings-${dark ? 'dark' : 'light'}.png`), fullPage: true })
  })
}
