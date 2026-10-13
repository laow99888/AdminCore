import { test, expect, type Page } from '@playwright/test'

const user = { id: 'u1', username: 'member', email: 'member@example.com', first_name: '', last_name: '', is_active: true, created_at: '2026-10-13T00:00:00Z', roles: [{ role__id: 'r1', role__name: '只读访客' }] }
const role = { id: 'r1', name: '只读访客', description: '', is_active: true, permissions: [] }
const menus = [{ id: 'm1', name: '菜单管理', path: '/menus', icon: 'list-tree', order: 1, parent: null, permission: null, is_visible: true, children: [] }, { id: 'm2', name: '用户管理', path: '/users', icon: 'users', order: 2, is_visible: true, children: [] }]
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const paged = (items: unknown[]) => envelope({ items, pagination: { total: items.length, page: 1, page_size: 100, total_pages: 1 } })

async function setup(page: Page, admin = true, permissionsFail = false) {
  await page.addInitScript(() => { localStorage.setItem('token', 'isolated-browser-fixture'); localStorage.setItem('locale', 'zh-CN') })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'a1', username: admin ? 'admin' : 'editor', is_staff: admin, is_superuser: admin, permissions: admin ? ['*'] : ['user:read', 'user:update', 'menu:read'] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope(menus) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (path.endsWith('/dashboard/stats/')) return route.fulfill({ json: envelope({ totals: { users: 50, active_users: 40, files: 10, pending_approvals: 2, today_logins: 8, today_operations: 9, unread_notifications: 0 }, login_trend: [{ date: '2026-10-13', success: 8, failed: 1 }], task_status: { success: 10 } }) })
    if (path.endsWith('/users/u1/')) return route.fulfill({ json: envelope(user) })
    if (path.endsWith('/users/')) return route.fulfill({ json: paged([user]) })
    if (path.endsWith('/roles/')) return route.fulfill({ json: paged([role]) })
    if (path.endsWith('/permissions/')) return route.fulfill(permissionsFail ? { status: 503, json: envelope(null) } : { json: paged([{ id: 'p1', name: '查看菜单', code: 'menu:read' }]) })
    if (path.endsWith('/menus/')) return route.fulfill({ json: paged(menus) })
    return route.fulfill({ json: envelope({}) })
  })
}

test('生产构建登录页可加载，必填校验有效', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/login')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('请输入用户名和密码')).toBeVisible()
  expect(errors).toEqual([])
})

test('管理员编辑用户保留原角色，提交携带 role_ids', async ({ page }) => {
  await setup(page)
  await page.goto('/users')
  await page.getByRole('button', { name: '编辑', exact: true }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('只读访客', { exact: true })).toBeVisible()
  const request = page.waitForRequest(request => request.method() === 'PATCH' && request.url().includes('/users/u1/'))
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  expect((await request).postDataJSON().role_ids).toEqual(['r1'])
})

test('普通编辑员无法从界面分配角色或维护菜单', async ({ page }) => {
  await setup(page, false)
  await page.goto('/users')
  await page.getByRole('button', { name: '编辑', exact: true }).first().click()
  await expect(page.getByRole('dialog').getByText('角色', { exact: true })).toHaveCount(0)
  await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click()
  await page.goto('/menus')
  await expect(page.getByRole('button', { name: '新增菜单', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '删除', exact: true })).toHaveCount(0)
})

test('菜单校验、创建请求和窄屏弹窗正常', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await setup(page)
  await page.goto('/menus')
  await page.getByRole('button', { name: '新增菜单', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const confirm = dialog.getByRole('button', { name: '确认', exact: true })
  await expect(confirm).toBeEnabled()
  await confirm.click()
  await expect(dialog.getByText('请输入菜单名')).toBeVisible()
  await dialog.getByLabel('菜单名', { exact: true }).fill('自定义菜单')
  await dialog.getByLabel('路由路径', { exact: true }).fill('/settings')
  const bounds = await dialog.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  const request = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/menus/'))
  await confirm.click()
  expect((await request).postDataJSON()).toMatchObject({ name: '自定义菜单', path: '/settings', parent: null, permission: null })
  await expect(dialog).not.toBeVisible()
  expect(errors).toEqual([])
})

test('权限加载失败显示错误并禁用保存', async ({ page }) => {
  await setup(page, true, true)
  await page.goto('/menus')
  await page.getByRole('button', { name: '新增菜单', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('权限加载失败，请重新打开编辑窗口')).toBeVisible()
  await expect(dialog.getByRole('button', { name: '确认', exact: true })).toBeDisabled()
})

test('仪表盘按需加载图表并正确渲染', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await setup(page)
  await page.goto('/')
  await expect(page.locator('canvas')).toHaveCount(2)
  await expect(page.getByText('近 7 日登录趋势')).toBeVisible()
  expect(errors).toEqual([])
})

test('暗色菜单编辑、取消和窄屏页面边界', async ({ page }) => {
  await setup(page)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/menus')
  await page.getByRole('button', { name: '切换到深色模式', exact: true }).click()
  await page.getByRole('button', { name: '编辑', exact: true }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('菜单名', { exact: true })).toHaveValue('菜单管理')
  await page.screenshot({ path: test.info().outputPath('menu-editor-dark.png'), fullPage: true })
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
