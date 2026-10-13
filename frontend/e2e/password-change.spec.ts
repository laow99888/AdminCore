import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, pending = true) {
  const state = { pending, failed: false, changeCalls: 0, businessCalls: [] as string[] }
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('password-fixture-started')) {
      sessionStorage.setItem('password-fixture-started', 'true')
      localStorage.setItem('token', 'isolated-password-fixture')
      localStorage.setItem('refreshToken', 'isolated-refresh-fixture')
    }
  })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: '中后台管理系统', logo: '' }) })
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'a1', username: 'fixture', permissions: ['*'], is_staff: true, must_change_password: state.pending }) })
    if (path.endsWith('/auth/logout/')) return route.fulfill({ json: envelope(null) })
    if (path.endsWith('/auth/change_password/')) {
      state.changeCalls++
      if (state.failed) return route.fulfill({ status: 400, json: { code: 400, message: '参数验证失败', data: { new_password: ['新密码不能与用户名过于相似'] } } })
      state.pending = false
      return route.fulfill({ json: envelope(null) })
    }
    state.businessCalls.push(path)
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/users/')) return route.fulfill({ json: envelope({ items: [{ id: 'u1', username: 'member', email: 'm@example.com' }], pagination: { total: 1, page: 1, page_size: 20, total_pages: 1 } }) })
    return route.fulfill({ json: envelope({}) })
  })
  return state
}

async function fillPassword(page: Page, value = 'Personal#Secure3782') {
  await page.getByLabel('当前密码', { exact: true }).fill('Initial#Secure8924')
  await page.getByLabel('新密码', { exact: true }).fill(value)
  await page.getByLabel('确认新密码', { exact: true }).fill(value)
}

test('深链接与刷新都先改密，不加载业务接口，手机无溢出', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/files')
  await expect(page).toHaveURL(/\/change-password$/)
  await expect(page.getByRole('heading', { name: '设置个人密码' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: '设置个人密码' })).toBeVisible()
  await page.goto('/users')
  await expect(page).toHaveURL(/\/change-password$/)
  expect(state.businessCalls).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('改密字段关联标签，拒绝原密码和不一致密码', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/change-password')
  await fillPassword(page, 'Initial#Secure8924')
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(page.getByText('新密码不能与当前密码相同')).toBeVisible()
  await fillPassword(page)
  await page.getByLabel('确认新密码', { exact: true }).fill('Different#8924')
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(page.getByText('两次输入的新密码不一致')).toBeVisible()
  expect(state.changeCalls).toBe(0)
})

test('服务端密码策略错误保留表单，并聚焦可访问错误提示', async ({ page }) => {
  const state = await setup(page)
  state.failed = true
  await page.goto('/change-password')
  await fillPassword(page)
  await page.getByRole('button', { name: '保存修改' }).click()
  const error = page.getByRole('alert').filter({ hasText: '新密码不能与用户名过于相似' })
  await expect(error).toBeVisible()
  await expect(error).toBeFocused()
  await expect(page.getByLabel('新密码', { exact: true })).toHaveValue('Personal#Secure3782')
  await expect(page).toHaveURL(/\/change-password$/)
})

test('改密成功清理两种凭据并回到登录页', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/change-password')
  await fillPassword(page)
  const sent = page.waitForRequest(request => request.url().endsWith('/auth/change_password/'))
  await page.getByRole('button', { name: '保存修改' }).click()
  expect((await sent).postDataJSON()).toEqual({ old_password: 'Initial#Secure8924', new_password: 'Personal#Secure3782', new_password2: 'Personal#Secure3782' })
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => [localStorage.getItem('token'), localStorage.getItem('refreshToken')])).toEqual([null, null])
  expect(state.changeCalls).toBe(1)
})

test('提交过程中禁用输入并阻止重复提交，允许退出', async ({ page }) => {
  await setup(page)
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  let calls = 0
  await page.route('**/auth/change_password/', async route => { calls++; await held; await route.fulfill({ status: 400, json: { code: 400, message: '旧密码不正确', data: null } }) })
  await page.goto('/change-password')
  await fillPassword(page)
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(page.getByLabel('当前密码', { exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '保存修改' })).toBeDisabled()
  release()
  await expect(page.locator('form [role="alert"]').filter({ hasText: '旧密码不正确' })).toBeVisible()
  expect(calls).toBe(1)
  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('旧账号继续访问设置，管理员重置可选择强制改密', async ({ page }) => {
  await setup(page, false)
  await page.goto('/change-password')
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByLabel('当前密码', { exact: true })).toBeVisible()
  await page.goto('/users')
  await page.getByRole('button', { name: '重置密码', exact: true }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('switch')).toBeChecked()
  await dialog.locator('.el-switch').click()
  await dialog.getByLabel('新密码', { exact: true }).fill('Reset#Secure8924')
  const sent = page.waitForRequest(request => request.url().endsWith('/reset_password/'))
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  expect((await sent).postDataJSON()).toEqual({ password: 'Reset#Secure8924', must_change_password: false })
  await expect(dialog).not.toBeVisible()
})

test('业务请求发现强制改密时重新读取用户，避开旧缓存', async ({ page }) => {
  const state = await setup(page, false)
  await page.goto('/settings')
  await expect(page.getByLabel('当前密码', { exact: true })).toBeVisible()
  state.pending = true
  await page.route('**/users/**', route => route.fulfill({ status: 403, json: { code: 403, message: '没有权限访问', data: { reason: 'password_change_required' } } }))
  await page.goto('/users')
  await expect(page).toHaveURL(/\/change-password$/)
  await expect(page.getByRole('heading', { name: '设置个人密码' })).toBeVisible()
})

test('每 30 秒刷新及窗口聚焦不离开改密页，不请求受限模块', async ({ page }) => {
  await page.clock.install()
  const state = await setup(page)
  await page.goto('/change-password')
  await expect(page.getByRole('heading', { name: '设置个人密码' })).toBeVisible()
  await page.clock.fastForward(31000)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page).toHaveURL(/\/change-password$/)
  expect(state.businessCalls).toEqual([])
})
