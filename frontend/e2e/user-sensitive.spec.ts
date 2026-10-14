import { test, expect, type Page } from '@playwright/test'

const raw = { email: 'original@example.test', phone: '13812341234' }
const masked = { email: 'o***@example.test', phone: '138****1234' }
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const user = { id: 'member-id', username: 'member', ...masked, first_name: 'Member', last_name: '', is_active: true, created_at: '2026-10-14T00:00:00Z', roles: [] }
async function setup(page: Page, options: { english?: boolean; permitted?: boolean } = {}) {
  const state = { permissions: options.permitted === false ? ['user:read', 'user:update'] : ['user:read', 'user:update', 'user:create', 'user:sensitive_read'],
    fail: false, hold: undefined as Promise<void> | undefined, reveals: [] as unknown[], writes: [] as { method: string; body: Record<string, unknown> }[] }
  await page.addInitScript(english => {
    localStorage.setItem('token', 'sensitive-admin-fixture'); localStorage.setItem('refreshToken', 'sensitive-refresh-fixture')
    if (english) { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') }
    const open = window.open.bind(window)
    window.open = (...args) => { const popup = open(...args); if (popup) popup.print = () => {}; return popup }
  }, options.english)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'admin-id', username: 'admin', is_staff: false, permissions: state.permissions }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/users/member-id/sensitive/')) {
      state.reveals.push(route.request().postDataJSON()); if (state.hold) await state.hold
      return route.fulfill({ status: state.fail ? 400 : 200, headers: { 'Cache-Control': 'no-store' }, json: envelope(state.fail ? null : raw) })
    }
    if ((path.endsWith('/users/member-id/') && method === 'PATCH') || (path.endsWith('/users/') && method === 'POST')) {
      state.writes.push({ method, body: route.request().postDataJSON() }); return route.fulfill({ json: envelope(user) })
    }
    if (path.endsWith('/users/member-id/')) return route.fulfill({ json: envelope(user) })
    if (path.endsWith('/users/')) return route.fulfill({ json: envelope({ items: [user], pagination: { page: 1, page_size: 10, total: 1, total_pages: 1 } }) })
    return route.fulfill({ json: envelope({}) })
  })
  return state
}
const viewButton = (page: Page) => page.getByRole('button', { name: '查看原值', exact: true })
const dialog = (page: Page) => page.getByRole('dialog')
const password = (page: Page) => dialog(page).getByRole('textbox', { name: '当前密码', exact: true })
async function reveal(page: Page) { await viewButton(page).click(); await password(page).fill('isolated-view-password'); await dialog(page).getByRole('button', { name: '确认查看', exact: true }).click(); await expect(dialog(page).getByText(raw.email, { exact: true })).toBeVisible() }

test('列表只脱敏，单次密码确认查看，取消与关闭清除，不持久化原值', async ({ page }) => {
  const state = await setup(page); await page.goto('/users')
  await expect(page.getByText(masked.email, { exact: true })).toBeVisible(); await expect(page.getByText(masked.phone, { exact: true })).toBeVisible()
  await expect(page.getByText(raw.email, { exact: true })).toHaveCount(0)
  await viewButton(page).click(); await password(page).fill('cancelled-password'); await dialog(page).getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog(page)).toHaveCount(0); expect(state.reveals).toHaveLength(0)
  await reveal(page); expect(state.reveals).toEqual([{ current_password: 'isolated-view-password' }])
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toMatch(/original@example|13812341234|isolated-view-password|cancelled-password/)
  await dialog(page).getByRole('button', { name: '关闭并清除' }).click(); await expect(dialog(page)).toHaveCount(0)
  await viewButton(page).click(); await expect(password(page)).toHaveValue(''); await expect(dialog(page).getByText(raw.email, { exact: true })).toHaveCount(0)
})

test('确认失败立即清密码可重试，确认中禁止重复提交与关闭', async ({ page }) => {
  const state = await setup(page); await page.goto('/users'); await viewButton(page).click(); state.fail = true
  await password(page).fill('wrong'); await dialog(page).getByRole('button', { name: '确认查看' }).click()
  await expect(dialog(page).getByRole('alert')).toContainText('原值查看未确认'); await expect(password(page)).toHaveValue('')
  state.fail = false; let release!: () => void; state.hold = new Promise(resolve => { release = resolve })
  await password(page).fill('isolated-view-password'); await dialog(page).getByRole('button', { name: '确认查看' }).click()
  await expect(password(page)).toHaveValue(''); await expect(dialog(page).getByRole('button', { name: '取消', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape'); await expect(dialog(page)).toBeVisible()
  await dialog(page).getByRole('button', { name: '确认查看' }).evaluate((button: HTMLButtonElement) => button.click())
  expect(state.reveals).toHaveLength(2); release(); await expect(dialog(page).getByText(raw.phone, { exact: true })).toBeVisible()
})

test('原值60秒到期自动销毁，再次查看需要重新确认密码', async ({ page }) => {
  await setup(page); await page.goto('/users'); await page.clock.install(); await reveal(page)
  await page.clock.fastForward(60_001); await expect(dialog(page)).toHaveCount(0); await expect(page.getByText(raw.email, { exact: true })).toHaveCount(0)
  await viewButton(page).click(); await expect(password(page)).toHaveValue('')
})

test('权限撤回即时销毁并隐藏按钮，跨标签身份切换不恢复迟到原值', async ({ page }) => {
  const state = await setup(page); await page.goto('/users'); await reveal(page)
  state.permissions = ['user:read', 'user:update']; await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(dialog(page)).toHaveCount(0); await expect(viewButton(page)).toHaveCount(0)
  state.permissions.push('user:sensitive_read'); await page.evaluate(() => window.dispatchEvent(new Event('focus'))); await expect(viewButton(page)).toBeVisible()
  let release!: () => void; state.hold = new Promise(resolve => { release = resolve }); await viewButton(page).click(); await password(page).fill('fixture'); await dialog(page).getByRole('button', { name: '确认查看' }).click()
  await page.evaluate(() => { localStorage.setItem('token', 'replacement-session'); window.dispatchEvent(new StorageEvent('storage', { key: 'token', oldValue: 'sensitive-admin-fixture', newValue: 'replacement-session' })) })
  await expect(dialog(page)).toHaveCount(0); release(); await expect(page.getByText(raw.email, { exact: true })).toHaveCount(0)
})

test('路由离开销毁未完成请求，后续响应不能打开旧窗口', async ({ page }) => {
  const state = await setup(page); await page.goto('/users'); let release!: () => void; state.hold = new Promise(resolve => { release = resolve })
  await viewButton(page).click(); await password(page).fill('fixture'); await dialog(page).getByRole('button', { name: '确认查看' }).click()
  await expect.poll(() => state.reveals.length).toBe(1)
  await page.evaluate(() => { location.hash = ''; history.pushState({}, '', '/settings'); window.dispatchEvent(new PopStateEvent('popstate')) })
  await expect(page).toHaveURL(/\/settings$/); await expect(dialog(page)).toHaveCount(0); release()
  await expect(page.getByText(raw.email, { exact: true })).toHaveCount(0)
})

test('编辑默认空输入保持联系方式，替换与清空电话明确，阻止提交mask', async ({ page }) => {
  const state = await setup(page); await page.goto('/users'); await page.getByRole('button', { name: '编辑', exact: true }).click()
  await expect(dialog(page).getByLabel('邮箱', { exact: true })).toHaveValue(''); await expect(dialog(page).getByLabel('电话', { exact: true })).toHaveValue('')
  await expect(dialog(page)).toContainText(masked.email)
  await dialog(page).getByRole('button', { name: '确认', exact: true }).click(); await expect(dialog(page)).toHaveCount(0)
  expect(state.writes[0]!.body).not.toHaveProperty('email'); expect(state.writes[0]!.body).not.toHaveProperty('phone')
  await page.getByRole('button', { name: '编辑', exact: true }).click(); await dialog(page).getByLabel('邮箱', { exact: true }).fill(masked.email)
  await dialog(page).getByRole('button', { name: '确认', exact: true }).click(); await expect(page.getByText('请输入完整的新邮箱或电话，不能提交脱敏值。', { exact: true })).toBeVisible(); expect(state.writes).toHaveLength(1)
  await dialog(page).getByLabel('邮箱', { exact: true }).fill('new@example.test'); await dialog(page).getByLabel('电话', { exact: true }).fill('13912341234')
  await dialog(page).getByRole('button', { name: '确认', exact: true }).click(); await expect(dialog(page)).toHaveCount(0)
  expect(state.writes[1]!.body).toMatchObject({ email: 'new@example.test', phone: '13912341234' })
  await page.getByRole('button', { name: '编辑', exact: true }).click(); await dialog(page).getByText('清空已保存电话', { exact: true }).click()
  await expect(dialog(page).getByRole('checkbox', { name: '清空已保存电话' })).toBeChecked()
  await expect(dialog(page).getByLabel('电话', { exact: true })).toBeDisabled(); await dialog(page).getByRole('button', { name: '确认', exact: true }).click(); await expect(dialog(page)).toHaveCount(0)
  expect(state.writes[2]!.body.phone).toBe(''); expect(state.writes[2]!.body).not.toHaveProperty('email')
})

test('创建邮箱必填，电话可选且只发送明确的新联系方式', async ({ page }) => {
  const state = await setup(page); await page.goto('/users'); await page.getByRole('button', { name: '+ 新增用户', exact: true }).click()
  await dialog(page).getByLabel('用户名', { exact: true }).fill('new-member'); await dialog(page).getByLabel('密码', { exact: true }).fill('isolated-new-password')
  await dialog(page).getByRole('button', { name: '确认', exact: true }).click(); expect(state.writes).toHaveLength(0)
  await dialog(page).getByLabel('邮箱', { exact: true }).fill('new@example.test'); await dialog(page).getByLabel('电话', { exact: true }).fill('13912341234')
  await dialog(page).getByRole('button', { name: '确认', exact: true }).click(); await expect(dialog(page)).toHaveCount(0)
  expect(state.writes[0]).toMatchObject({ method: 'POST', body: { email: 'new@example.test', phone: '13912341234' } })
})

test('临时查看后打印仍仅包含mask，无权限时隐藏原值入口', async ({ page }) => {
  await setup(page); await page.goto('/users'); await reveal(page); await dialog(page).getByRole('button', { name: '关闭并清除' }).click(); await expect(dialog(page)).toHaveCount(0)
  const opened = page.waitForEvent('popup'); await page.getByRole('button', { name: '打印 / 保存 PDF（当前页）', exact: true }).click(); const popup = await opened
  await expect(popup.locator('tbody')).toContainText(masked.email); await expect(popup.locator('tbody')).toContainText(masked.phone)
  await expect(popup.locator('body')).not.toContainText(raw.email); await expect(popup.locator('body')).not.toContainText(raw.phone); await popup.close()
})

test('英文窄屏原值窗口可读，无权限没有入口与请求', async ({ page }, info) => {
  const state = await setup(page, { english: true, permitted: false }); await page.goto('/users')
  await expect(page.getByText(masked.email, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'View Original Values' })).toHaveCount(0); expect(state.reveals).toHaveLength(0)
  state.permissions.push('user:sensitive_read'); await page.reload()
  await page.getByRole('button', { name: 'View Original Values' }).click(); await dialog(page).getByRole('textbox', { name: 'Current Password', exact: true }).fill('fixture')
  await dialog(page).getByRole('button', { name: 'Confirm Viewing' }).click(); await expect(dialog(page).getByText(raw.email, { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('user-sensitive-english.png'), fullPage: true, animations: 'disabled' })
})
