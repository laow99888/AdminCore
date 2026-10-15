import { expect, test, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const userId = '10000000-0000-4000-8000-000000000001'
async function setup(page: Page, administrator = false) {
  const state = { enabled: true, configFail: false, completeFail: false, bindFail: false, permission: true, staff: true, revoked: false,
    completed: [] as Record<string, unknown>[], bindings: [] as Record<string, unknown>[], unbindings: [] as Record<string, unknown>[] }
  if (administrator) await page.addInitScript(() => { localStorage.setItem('token', 'sso-manager-fixture'); localStorage.setItem('refreshToken', 'sso-manager-refresh') })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: userId, username: 'existing-local', avatar: '', email: '', is_staff: state.staff, permissions: state.permission ? ['*'] : ['sso:read'] }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'sso', title: '企业身份登录', enabled: state.enabled, dependencies: [], paths: ['/integrations/identities', '/enterprise-login'], page_permissions: { '/integrations/identities': 'sso:read' } }] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/sso/config/')) return route.fulfill({ status: state.configFail ? 503 : 200, json: envelope({ enabled: state.enabled, label: 'Company SSO' }) })
    if (path.endsWith('/sso/status/')) return route.fulfill({ json: envelope({ ready: true, mfa_required: true, captcha: { required: false } }) })
    if (path.endsWith('/sso/complete/')) {
      state.completed.push(route.request().postDataJSON())
      expect(route.request().headers().authorization).toBeUndefined()
      return route.fulfill({ status: state.completeFail ? 401 : 200, json: state.completeFail ? { code: 401, message: '认证失败', data: { code: 'mfa_invalid' } } : envelope({ access: 'completed-sso-fixture', refresh: 'completed-refresh-fixture', user: { id: userId, username: 'existing-local', avatar: '', email: '' } }) })
    }
    if (path.endsWith('/sso/identities/') && route.request().method() === 'POST') {
      state.bindings.push(route.request().postDataJSON())
      return route.fulfill({ status: state.bindFail ? 400 : 201, json: state.bindFail ? { code: 400, message: '绑定重复', data: null } : envelope({ id: userId }) })
    }
    if (path.endsWith('/sso/identities/')) return route.fulfill({ json: envelope({ items: [{ id: userId, user_id: userId, username: 'existing-local', issuer: 'https://idp.example', subject: 'immutable-subject', created_at: '', revoked_at: state.revoked ? '2026-10-16T00:00:00Z' : null }], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } }) })
    if (path.endsWith('/unbind/')) { state.unbindings.push(route.request().postDataJSON()); state.revoked = true; return route.fulfill({ json: envelope(null) }) }
    if (path.endsWith('/auth/password-recovery/config/')) return route.fulfill({ json: envelope({ enabled: false }) })
    if (path.endsWith('/auth/login-captcha/')) return route.fulfill({ json: envelope({ required: false }) })
    return route.fulfill({ json: envelope({}) })
  })
  return state
}

test('企业授权后仍需本地动态码；失败可重试且安全证明不进入浏览器存储', async ({ page }, info) => {
  const state = await setup(page)
  await page.goto('/enterprise-login?result=ready')
  await expect(page.getByRole('heading', { name: '企业身份登录', exact: true })).toBeVisible()
  const code = page.getByRole('textbox', { name: '动态码或恢复码', exact: true })
  await expect(page.getByRole('button', { name: '验证并登录', exact: true })).toBeDisabled()
  expect(state.completed).toHaveLength(0)
  state.completeFail = true
  await code.fill('123456'); await page.getByRole('button', { name: '验证并登录', exact: true }).click()
  await expect(code).toHaveValue('')
  await expect(page.getByRole('alert')).toContainText('认证码无效')
  expect(state.completed).toEqual([{ otp_code: '123456' }])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('sso-local-security.png'), fullPage: true })
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain('123456')
  state.completeFail = false
  await code.fill('654321'); await page.getByRole('button', { name: '验证并登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  expect(state.completed).toHaveLength(2)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBe('completed-sso-fixture')
})

test('供应商配置故障或模块关闭仍可返回本地登录', async ({ page }) => {
  const state = await setup(page)
  state.configFail = true
  await page.goto('/enterprise-login')
  await expect(page.getByRole('alert')).toContainText('本地登录')
  await page.getByRole('button', { name: '使用本地账号登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByPlaceholder('用户名', { exact: true })).toBeVisible()
  state.configFail = false; state.enabled = false
  await page.goto('/enterprise-login')
  await expect(page.getByText('企业登录未启用，请使用本地账号登录。', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '前往企业认证', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('管理员显式绑定需再次密码确认；重复失败清密码，撤销禁用行按钮', async ({ page }, info) => {
  const state = await setup(page, true)
  await page.goto('/integrations/identities')
  await expect(page.getByRole('heading', { name: '企业身份绑定', exact: true })).toBeVisible()
  const button = page.getByRole('button', { name: '确认绑定', exact: true })
  await expect(button).toBeDisabled()
  await page.getByRole('textbox', { name: '本地用户 UUID', exact: true }).fill(userId)
  await page.getByRole('textbox', { name: '供应商 subject', exact: true }).fill('new-immutable-subject')
  await button.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('button', { name: '确认绑定', exact: true })).toBeDisabled()
  state.bindFail = true
  await dialog.getByRole('textbox', { name: '当前密码', exact: true }).fill('fixture-current-password')
  await dialog.getByRole('button', { name: '确认绑定', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('绑定操作未确认')
  await expect(dialog.getByRole('textbox', { name: '当前密码', exact: true })).toHaveValue('')
  state.bindFail = false
  await dialog.getByRole('textbox', { name: '当前密码', exact: true }).fill('fixture-current-password')
  await dialog.getByRole('button', { name: '确认绑定', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(state.bindings[0]).toEqual({ user_id: userId, subject: 'new-immutable-subject', current_password: 'fixture-current-password' })
  const row = page.getByRole('row').filter({ hasText: 'existing-local' })
  await row.getByRole('button', { name: '撤销企业绑定', exact: true }).click()
  await dialog.getByRole('textbox', { name: '当前密码', exact: true }).fill('fixture-current-password')
  await dialog.getByRole('button', { name: '撤销企业绑定', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(state.unbindings).toEqual([{ current_password: 'fixture-current-password' }])
  await expect(row.getByRole('button', { name: '撤销企业绑定', exact: true })).toBeDisabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('sso-identities.png'), fullPage: true })
})

test('非管理员或仅查看权限不展示绑定和撤销，关闭模块拒绝管理页面', async ({ page }) => {
  const state = await setup(page, true)
  state.staff = false
  await page.goto('/integrations/identities')
  await expect(page.getByRole('heading', { name: '企业身份绑定', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '确认绑定', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '撤销企业绑定', exact: true })).toHaveCount(0)
  state.staff = true; state.permission = false
  await page.reload()
  await expect(page.getByRole('heading', { name: '企业身份绑定', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '确认绑定', exact: true })).toHaveCount(0)
  state.enabled = false
  await page.reload()
  await expect(page).toHaveURL(/\/$/)
})
