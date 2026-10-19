import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, options: { enabled?: boolean; english?: boolean; storageBlocked?: boolean } = {}) {
  const state = { permissions: ['*'], files: true, mustChange: false }
  await page.addInitScript(options => {
    // Init scripts run again after goto/reload: seed once so logout and persisted choices survive.
    if (!sessionStorage.getItem('shortcuts-fixture-initialized')) {
      localStorage.setItem('token', 'isolated-shortcut-fixture')
      if (options.enabled) localStorage.setItem('admincore:keyboard-shortcuts', 'true')
      if (options.english) { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') }
      sessionStorage.setItem('shortcuts-fixture-initialized', 'true')
    }
    if (options.storageBlocked) {
      const original = Storage.prototype.setItem
      Storage.prototype.setItem = function (key, value) {
        if (key === 'admincore:keyboard-shortcuts') throw new Error('fixture quota')
        original.call(this, key, value)
      }
    }
  }, options)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    const user = { id: 'shortcuts-member', username: 'member', email: 'm@example.test', avatar: '', first_name: '', last_name: '', phone: '', bio: '',
      is_staff: true, permissions: state.permissions, profile_version: 1, has_avatar: false, avatar_enabled: false, must_change_password: state.mustChange }
    if (path.endsWith('/auth/me/') || path.endsWith('/auth/profile/')) return route.fulfill({ json: envelope(user) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'files', enabled: state.files, paths: ['/files'], dependencies: [] }] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'u', name: '用户管理', path: '/users', icon: 'users' }, { id: 'r', name: '角色权限', path: '/roles', icon: 'shield' }, { id: 'f', name: '文件管理', path: '/files', icon: 'folder' }, { id: 's', name: '系统设置', path: '/settings' }]) })
    if (path.endsWith('/dashboard/stats/')) return route.fulfill({ json: envelope({ totals: {}, login_trend: [], task_status: {} }) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    return route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 20, total_pages: 0 } }) })
  })
  return state
}
const helpButton = (page: Page, english = false) => page.getByRole('button', { name: english ? 'Keyboard Shortcuts Help' : '快捷键帮助', exact: true })
const helpDialog = (page: Page, english = false) => page.getByRole('dialog', { name: english ? 'Keyboard Shortcuts Help' : '快捷键帮助', exact: true })
async function closeHelp(page: Page) {
  await page.keyboard.press('Escape')
  await expect(helpDialog(page)).not.toBeVisible()
  // Shortcut suppression also covers closing overlays, beyond dialog-content visibility.
  await expect(page.locator('.el-overlay:visible')).toHaveCount(0)
}
async function focusPage(page: Page) {
  // Narrow headers keep their title available to assistive technology only.
  // Click the content padding to leave text fields without activating a control.
  await page.locator('.layout-content').click({ position: { x: 8, y: 8 } })
}
async function sidebar(page: Page, path: string) {
  if (page.viewportSize()!.width <= 768) await page.getByRole('button', { name: /打开菜单|Open Menu/ }).click()
  await page.locator(`.sidebar-menu a[href="${path}"]`).click()
  await expect(page).toHaveURL(new RegExp(`${path}$`))
}

test('鼠标发现帮助、默认关闭、Space启用与刷新持久化；关闭不影响鼠标导航', async ({ page }) => {
  await setup(page)
  await page.goto('/users')
  await focusPage(page); await page.keyboard.press('Alt+Shift+H')
  await expect(page).toHaveURL(/\/users$/)
  await helpButton(page).click()
  const dialog = helpDialog(page), enabled = dialog.getByRole('switch', { name: '启用键盘快捷键', exact: true })
  await expect(dialog).toContainText('默认关闭')
  await expect(enabled).toHaveAttribute('aria-checked', 'false')
  await enabled.focus(); await page.keyboard.press('Space')
  await expect(enabled).toHaveAttribute('aria-checked', 'true')
  await closeHelp(page)
  await focusPage(page); await page.keyboard.press('Alt+Shift+S'); await expect(page).toHaveURL(/\/settings$/)
  await page.reload(); await helpButton(page).click()
  await expect(helpDialog(page).getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  await helpDialog(page).locator('.el-switch').click()
  await closeHelp(page)
  await focusPage(page); await page.keyboard.press('Alt+Shift+H'); await expect(page).toHaveURL(/\/settings$/)
  await sidebar(page, '/users'); await expect(page).toHaveURL(/\/users$/)
  expect(await page.evaluate(() => localStorage.getItem('admincore:keyboard-shortcuts'))).toBe('false')
})

test('相邻页签切换、关闭清理与首页固定；输入和打开的弹窗不触发快捷键', async ({ page }) => {
  await setup(page, { enabled: true })
  await page.goto('/users'); await sidebar(page, '/roles')
  await focusPage(page); await page.keyboard.press('Alt+Shift+ArrowLeft'); await expect(page).toHaveURL(/\/users$/)
  await focusPage(page); await page.keyboard.press('Alt+Shift+ArrowRight'); await expect(page).toHaveURL(/\/roles$/)
  await focusPage(page); await page.keyboard.press('Alt+Shift+W'); await expect(page).toHaveURL(/\/users$/)
  await expect(page.locator('.navigation-tab[data-path="/roles"]')).toHaveCount(0)
  await page.getByPlaceholder('搜索用户名 / 姓名').focus(); await page.keyboard.press('Alt+Shift+H')
  await expect(page).toHaveURL(/\/users$/)
  await page.keyboard.type('?'); await expect(helpDialog(page)).not.toBeVisible()
  await helpButton(page).click(); await page.keyboard.press('Alt+Shift+H'); await expect(page).toHaveURL(/\/users$/)
  await closeHelp(page)
  // Slash names the physical key; '/' explicitly requests an unshifted character in Playwright.
  await focusPage(page); await page.keyboard.press('Shift+Slash'); await expect(helpDialog(page)).toBeVisible()
  await closeHelp(page)
  await focusPage(page); await page.keyboard.press('Alt+Shift+H'); await expect(page).toHaveURL(/\/$/)
  await page.keyboard.press('Alt+Shift+W'); await expect(page).toHaveURL(/\/$/)
  await expect(page.locator('.navigation-tab[data-path="/"]')).toBeVisible()
})

test('快捷键关闭当前页签服从未保存资料守卫，取消保留输入和页签', async ({ page }) => {
  await setup(page, { enabled: true })
  await page.goto('/users'); await sidebar(page, '/settings')
  await page.getByLabel('名字', { exact: true }).fill('dirty-shortcut')
  await focusPage(page); await page.keyboard.press('Alt+Shift+W')
  await expect(page.getByText('尚有未保存的资料，确定放弃修改吗？')).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('dirty-shortcut')
  await expect(page.locator('.navigation-tab[data-path="/settings"]')).toBeVisible()
  await focusPage(page); await page.keyboard.press('Alt+Shift+W')
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page).toHaveURL(/\/users$/)
  await expect(page.locator('.navigation-tab[data-path="/settings"]')).toHaveCount(0)
})

test('权限和模块刷新清除受限页签；公共登录页与强制改密页不启用', async ({ page }) => {
  const state = await setup(page, { enabled: true })
  await page.goto('/users'); await sidebar(page, '/files'); await sidebar(page, '/roles')
  state.permissions = ['role:read']; state.files = false
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.locator('.navigation-tab[data-path="/users"]')).toHaveCount(0)
  await expect(page.locator('.navigation-tab[data-path="/files"]')).toHaveCount(0)
  await focusPage(page); await page.keyboard.press('Alt+Shift+ArrowLeft'); await expect(page).toHaveURL(/\/$/)
  state.mustChange = true
  await page.goto('/users'); await expect(page).toHaveURL(/\/change-password$/)
  await expect(helpButton(page)).toHaveCount(0)
  await page.keyboard.press('Alt+Shift+H'); await expect(page).toHaveURL(/\/change-password$/)
  await page.evaluate(() => { localStorage.removeItem('token'); localStorage.removeItem('refreshToken') })
  await page.goto('/login'); await expect(helpButton(page)).toHaveCount(0)
  await page.keyboard.press('Alt+Shift+S'); await expect(page).toHaveURL(/\/login$/)
})

test('英文深色帮助支持窄屏，存储异常提示且本次启用可使用', async ({ page }) => {
  await setup(page, { english: true, storageBlocked: true })
  await page.goto('/users'); await helpButton(page, true).click()
  // Exercise the interval where the dialog is hidden but its closing overlay still exists.
  await page.addStyleTag({ content: '.el-overlay.dialog-fade-leave-active { animation-duration: 1s !important; animation-play-state: paused !important; pointer-events: none; } .dialog-fade-leave-active .el-overlay-dialog { visibility: hidden; }' })
  const dialog = helpDialog(page, true)
  await expect(dialog).toContainText('Previous tab')
  await expect(dialog).toContainText('Alt + Shift + W')
  await dialog.locator('.el-switch').click()
  await expect(dialog.getByRole('status')).toContainText('current page session')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('keyboard-help-english-dark.png'), fullPage: true })
  await page.keyboard.press('Escape'); await expect(dialog).not.toBeVisible()
  const closingOverlay = page.locator('.el-overlay.dialog-fade-leave-active')
  await expect(closingOverlay).toBeVisible()
  await focusPage(page); await page.keyboard.press('Alt+Shift+H'); await expect(page).toHaveURL(/\/users$/)
  await closingOverlay.evaluate(element => (element as HTMLElement).style.setProperty('animation-play-state', 'running', 'important'))
  await expect(page.locator('.el-overlay:visible')).toHaveCount(0)
  await focusPage(page); await page.keyboard.press('Alt+Shift+H'); await expect(page).toHaveURL(/\/$/)
})
