import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, english = false) {
  const state = { permissions: ['*'], files: true, failUsers: false, userId: 'navigation-admin' }
  await page.addInitScript(({ english }) => {
    localStorage.setItem('token', 'isolated-navigation-fixture')
    if (english) { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') }
  }, { english })
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: state.userId, username: 'admin', is_staff: true, permissions: state.permissions }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: ['files', 'tasks', 'notifications', 'system'].map(key => ({ key, enabled: key !== 'files' || state.files, paths: key === 'system' ? ['/system'] : [`/${key}`], dependencies: [], ...(key === 'files' ? { page_permissions: { '/files': 'file:read' } } : {}) })) }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'u', name: '用户管理', path: '/users', icon: 'users' }, { id: 'r', name: '角色权限', path: '/roles', icon: 'shield' }, { id: 'f', name: '文件管理', path: '/files', icon: 'folder' }, { id: 'l', name: '操作日志', path: '/logs', icon: 'logs' }]) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (path.endsWith('/dashboard/stats/')) return route.fulfill({ json: envelope({ totals: {}, login_trend: [{ date: '2026-10-16', success: 2, failed: 1 }], task_status: {} }) })
    if (path.endsWith('/auth/logout/')) return route.fulfill({ json: envelope({}) })
    const current = Number(url.searchParams.get('page') || 1), size = Number(url.searchParams.get('page_size') || 10)
    let items: unknown[] = []
    if (path.endsWith('/users/')) {
      if (state.failUsers) return route.fulfill({ status: 503, json: { code: 503, message: 'fixture unavailable', data: null } })
      items = [{ id: 'u1', username: `member-page-${current}`, email: 'member@example.com', is_active: true, roles: [], first_name: '', last_name: '' }]
    }
    if (path.endsWith('/roles/')) items = [{ id: 'r1', name: '只读访客', is_active: true, description: '' }]
    if (path.includes('/logs/')) items = [{ id: 'l1', description: `log-page-${current}`, username: `log-page-${current}`, status: 'success', resource: 'user', action: 'read', created_at: '2026-10-14' }]
    return route.fulfill({ json: envelope({ items, pagination: { total: 41, page: current, page_size: size, total_pages: Math.ceil(41 / size) } }) })
  })
  return state
}
const tabs = (page: Page) => page.locator('.navigation-shell .navigation-tab')

test('菜单搜索支持键盘选择、无结果和手机入口，受当前权限约束', async ({ page }) => {
  const state = await setup(page)
  state.permissions = ['user:read']
  await page.goto('/')
  const mobile = page.viewportSize()!.width <= 768
  if (mobile) await page.getByRole('button', { name: '搜索菜单', exact: true }).click()
  const input = page.locator('input[aria-label="搜索菜单"]:visible')
  await input.fill('管理')
  const results = page.locator('.el-autocomplete-suggestion:visible')
  await expect(results).toContainText('用户管理')
  await expect(results).not.toContainText('文件管理')
  await input.press('ArrowDown')
  await input.press('Enter')
  await expect(page).toHaveURL(/\/users$/)
  if (mobile) await expect(page.getByRole('dialog', { name: '搜索菜单', exact: true })).not.toBeVisible()
  if (mobile) await page.getByRole('button', { name: '搜索菜单', exact: true }).click()
  const currentInput = mobile ? page.getByRole('dialog', { name: '搜索菜单', exact: true }).getByRole('textbox') : input
  await currentInput.fill('不存在的菜单')
  await expect(page.locator('.menu-search')).toContainText('没有匹配的菜单')
  expect(await page.locator('.app-header').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
})

test('仪表盘图表提供键盘可展开的数据表', async ({ page }) => {
  await setup(page)
  await page.goto('/')
  const details = page.locator('.chart-data').first()
  await details.locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(details.locator('table')).toBeVisible()
  await expect(details.locator('caption')).toHaveText('近 7 日登录趋势')
})

async function switchTo(page: Page, path: string) { await page.locator(`.navigation-tab[data-path="${path}"]`).click() }
async function openFromSidebar(page: Page, path: string) {
  if (page.viewportSize()!.width <= 768) await page.getByRole('button', { name: /打开菜单|Open Menu/ }).click()
  await page.locator(`.sidebar-menu a[href="${path}"]`).click()
  await expect(page).toHaveURL(new RegExp(`${path}$`))
  await expect(page.locator(`.navigation-tab[data-path="${path}"]`)).toHaveAttribute('aria-current', 'page')
}

test('切换页签和浏览器返回恢复用户筛选、页码并重新取数', async ({ page }) => {
  await setup(page)
  await page.goto('/users')
  const input = page.getByPlaceholder('搜索用户名 / 姓名')
  await input.fill('member')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.locator('.el-pagination__sizes .el-select__wrapper').click()
  await page.getByRole('option', { name: '20条/页', exact: true }).click()
  await page.locator('.el-pager .number').filter({ hasText: /^3$/ }).click()
  await expect(page.getByText('member-page-3', { exact: true })).toBeVisible()
  await openFromSidebar(page, '/roles')
  const request = page.waitForRequest(req => { const url = new URL(req.url()); return url.pathname.endsWith('/users/') && url.searchParams.get('page') === '3' && url.searchParams.get('page_size') === '20' && url.searchParams.get('search') === 'member' })
  await switchTo(page, '/users')
  await request
  await expect(input).toHaveValue('member')
  await expect(page.locator('.el-pagination__sizes')).toContainText('20条/页')
  await expect(page.locator('.navigation-tab[data-path="/users"]')).toHaveAttribute('aria-current', 'page')
  await page.goBack()
  await expect(page).toHaveURL(/\/roles$/)
  await page.goForward()
  await expect(page.getByText('member-page-3', { exact: true })).toBeVisible()
  expect(await tabs(page).count()).toBe(3)
})

test('关闭当前页签跳到相邻页，重新打开清除查询；首页固定', async ({ page }) => {
  await setup(page)
  await page.goto('/roles')
  await openFromSidebar(page, '/users')
  await page.getByPlaceholder('搜索用户名 / 姓名').fill('private-filter')
  await page.getByRole('button', { name: '关闭页签 用户管理', exact: true }).click()
  await expect(page).toHaveURL(/\/roles$/)
  await expect(page.locator('.navigation-tab[data-path="/users"]')).toHaveCount(0)
  await openFromSidebar(page, '/users')
  await expect(page.getByPlaceholder('搜索用户名 / 姓名')).toHaveValue('')
  await expect(page.getByRole('button', { name: '关闭页签 仪表盘' })).toHaveCount(0)
})

test('右键关闭其他先切换目标，再保留目标与首页', async ({ page }) => {
  await setup(page)
  await page.goto('/users')
  await openFromSidebar(page, '/roles')
  await page.locator('.navigation-tab[data-path="/users"]').click({ button: 'right' })
  await page.getByRole('button', { name: '关闭其他页签', exact: true }).click()
  await expect(page).toHaveURL(/\/users$/)
  await expect(tabs(page)).toHaveCount(2)
  await expect(page.locator('.navigation-tab[data-path="/roles"]')).toHaveCount(0)
})

test('键盘菜单可打开、Escape恢复焦点；触屏操作入口可关闭其他', async ({ page }) => {
  await setup(page)
  await page.goto('/users')
  await openFromSidebar(page, '/roles')
  const target = page.locator('.navigation-tab[data-path="/roles"]')
  await target.focus()
  await page.keyboard.press('Shift+F10')
  await expect(page.getByRole('button', { name: '关闭其他页签', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(target).toBeFocused()
  await page.getByRole('button', { name: '页签操作', exact: true }).click()
  await page.getByRole('button', { name: '关闭其他页签', exact: true }).click()
  await expect(tabs(page)).toHaveCount(2)
})

test('面包屑展示父级并能返回；状态仅在当前页面会话存活', async ({ page }) => {
  await setup(page)
  await page.goto('/files/recycle')
  const breadcrumb = page.locator('.breadcrumb-row')
  await expect(breadcrumb).toContainText('文件回收站')
  await breadcrumb.getByRole('link', { name: '文件管理', exact: true }).click()
  await expect(page).toHaveURL(/\/files$/)
  await breadcrumb.getByRole('link', { name: '首页', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(tabs(page)).toHaveCount(3)
  await page.reload()
  await expect(tabs(page)).toHaveCount(1)
  expect(await page.evaluate(() => localStorage.getItem('admincore:navigation-tabs') || sessionStorage.getItem('admincore:navigation-tabs'))).toBeNull()
})

test('日志页面真实 KeepAlive；恢复视角和页码，重新激活取最新数据', async ({ page }) => {
  await setup(page)
  await page.goto('/logs')
  await page.getByRole('tab', { name: '登录日志', exact: true }).click()
  await page.locator('.el-pager .number').filter({ hasText: /^2$/ }).click()
  await expect(page.getByText('log-page-2', { exact: true })).toBeVisible()
  await page.locator('.log-container').evaluate(element => { element.setAttribute('data-cached-fixture', 'retained') })
  await openFromSidebar(page, '/users')
  const request = page.waitForRequest(req => req.url().includes('/logs/login/') && new URL(req.url()).searchParams.get('page') === '2')
  await switchTo(page, '/logs')
  await request
  await expect(page.locator('.log-container')).toHaveAttribute('data-cached-fixture', 'retained')
  await expect(page.getByText('log-page-2', { exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: '登录日志', exact: true })).toHaveAttribute('aria-selected', 'true')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('navigation-log-pagination.png'), fullPage: true })
})

test('后台页签撤权/模块关闭立即清除，旧入口不能重新打开', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/users')
  await openFromSidebar(page, '/files')
  await openFromSidebar(page, '/roles')
  state.permissions = ['role:read']
  state.files = false
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.locator('.navigation-tab[data-path="/users"]')).toHaveCount(0)
  await expect(page.locator('.navigation-tab[data-path="/files"]')).toHaveCount(0)
  await expect(page.locator('.navigation-tab[data-path="/roles"]')).toBeVisible()
  await page.goto('/users')
  await expect(page).toHaveURL(/\/403$/)
  await page.goto('/files')
  await expect(page).toHaveURL(/\/$/)
})

test('列表请求失败可重试，导航不丢查询；退出清会话与页签', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/users')
  await page.getByPlaceholder('搜索用户名 / 姓名').fill('retained')
  state.failUsers = true
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page.getByText('fixture unavailable', { exact: true })).toBeVisible()
  state.failUsers = false
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page.getByText('member-page-1', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '用户菜单', exact: true }).click()
  await page.getByText('退出登录', { exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.locator('.navigation-shell')).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
})

test('同浏览器账号改变后清空上一账号查询和缓存', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/users')
  await page.getByPlaceholder('搜索用户名 / 姓名').fill('previous-account')
  await openFromSidebar(page, '/roles')
  state.userId = 'another-account'
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.locator('.navigation-tab[data-path="/users"]')).toHaveCount(0)
  await openFromSidebar(page, '/users')
  await expect(page.getByPlaceholder('搜索用户名 / 姓名')).toHaveValue('')
})

test('英文深色、横向页签与语言切换，桌面及375px无页面溢出', async ({ page }, info) => {
  await setup(page, true)
  await page.goto('/users')
  await openFromSidebar(page, '/roles')
  await openFromSidebar(page, '/files')
  await expect(page.locator('.breadcrumb-row').getByRole('link', { name: 'Home', exact: true })).toBeVisible()
  await expect(page.locator('.navigation-tab[data-path="/files"]')).toHaveText('File Management')
  await page.getByRole('button', { name: 'Change Language', exact: true }).click()
  await page.getByText('中文', { exact: true }).click()
  await expect(page.locator('.navigation-tab[data-path="/files"]')).toHaveText('文件管理')
  await expect(page.locator('html')).toHaveClass(/dark/)
  const strip = await page.locator('.tabs-row').boundingBox()
  const close = await page.getByRole('button', { name: '关闭页签 文件管理', exact: true }).boundingBox()
  expect(close!.x).toBeGreaterThanOrEqual(strip!.x)
  expect(close!.x + close!.width).toBeLessThanOrEqual(strip!.x + strip!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('navigation-dark.png'), fullPage: true })
})
