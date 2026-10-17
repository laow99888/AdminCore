import { test, expect, type Page } from '@playwright/test'
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const jwt = (sid: string) => `fixture.${Buffer.from(JSON.stringify({ sid, user_id: 'member', session_version: 1 })).toString('base64url')}.fixture`
const seed = 'ABCDEFGHIJKLMNOPQRSTUVWX234567AB'
const codes = Array.from({ length: 10 }, (_, index) => index.toString(16).padStart(32, 'a'))
async function setup(page: Page, authenticated = true, english = false) {
  const state = { enabled: false, available: true, fail: false, statusFail: false, loginStatus: 0, logins: [] as Record<string, unknown>[], writes: [] as { path: string; body: unknown }[], setupExpires: 600,
    hold: undefined as Promise<void> | undefined, user: { id: 'member', username: 'member', email: '', avatar: '', is_staff: false, permissions: [], totp_enabled: false } }
  await page.addInitScript(({ authenticated, english, access }) => {
    if (authenticated && !localStorage.getItem('token')) { localStorage.setItem('token', access); localStorage.setItem('refreshToken', 'fixture-refresh') }
    if (english) localStorage.setItem('language', 'en-US')
  }, { authenticated, english, access: jwt('old') })
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope(state.user) })
    if (path.endsWith('/auth/login/')) {
      const body = req.postDataJSON(); state.logins.push(body)
      if (state.hold) await state.hold
      if (!body.otp_code) return route.fulfill({ status: 401, json: { code: 401, message: '认证失败', data: { code: 'mfa_required', detail: '需要双因素认证' } } })
      if (state.loginStatus) return route.fulfill({ status: state.loginStatus, json: { code: state.loginStatus, message: '暂不可用', data: null } })
      if (body.otp_code !== '123456' && body.otp_code !== codes[0]) return route.fulfill({ status: 401, json: { code: 401, message: '认证失败', data: null } })
      return route.fulfill({ json: { access: jwt('login'), refresh: 'login-refresh', user: state.user } })
    }
    if (path.endsWith('/auth/totp/')) return route.fulfill({ status: state.statusFail ? 503 : 200, json: envelope({ enabled: state.enabled, available: state.available, recovery_codes_remaining: state.enabled ? 10 : 0 }) })
    if (path.includes('/auth/totp/')) {
      state.writes.push({ path, body: req.postDataJSON() }); if (state.hold) await state.hold
      if (state.fail) return route.fulfill({ status: 400, json: { code: 400, message: '凭据错误', data: null } })
      if (path.endsWith('/setup/')) return route.fulfill({ json: envelope({ secret: seed, otpauth_uri: `otpauth://totp/AdminCore:member?secret=${seed}&issuer=AdminCore`, expires_at: new Date(Date.now() + state.setupExpires * 1000).toISOString() }) })
      state.enabled = !path.endsWith('/disable/'); state.user = { ...state.user, totp_enabled: state.enabled }
      return route.fulfill({ json: envelope({ access: jwt(`security-${state.writes.length}`), refresh: `security-refresh-${state.writes.length}`, user: state.user, ...(state.enabled ? { recovery_codes: codes } : {}) }) })
    }
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: '现代化中后台管理系统' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'settings', name: '系统设置', path: '/settings', children: [] }]) })
    if (path.endsWith('/auth/recovery/config/')) return route.fulfill({ json: envelope({ enabled: false }) })
    if (path.endsWith('/auth/profile/')) return route.fulfill({ json: envelope({ ...state.user, first_name: '', last_name: '', phone: '', bio: '', profile_version: 1, has_avatar: false, avatar_enabled: false }) })
    return route.fulfill({ json: envelope({ count: 0, totals: {}, login_trend: [], task_status: {} }) })
  })
  return state
}
async function start(page: Page) { await page.getByRole('textbox', { name: '当前密码', exact: true }).fill('isolated-password'); await page.getByRole('button', { name: '生成认证器密钥' }).click(); await expect(page.getByText(seed, { exact: true })).toBeVisible() }
async function enable(page: Page) { await start(page); await page.getByRole('textbox', { name: '当前密码', exact: true }).fill('isolated-password'); await page.getByRole('textbox', { name: '认证器动态码', exact: true }).fill('123456'); await page.getByRole('button', { name: '确认启用双因素认证' }).click(); await expect(page.getByRole('heading', { name: '保存一次性恢复码' })).toBeVisible() }
async function settingsLink(page: Page) { if (page.viewportSize()!.width <= 768) await page.getByRole('button', { name: '打开菜单' }).click(); await page.locator('.sidebar-menu a[href="/settings"]').click() }

test('双因素登录缺码无JWT，失败清码可重试并接受恢复码', async ({ page }) => {
  const state = await setup(page, false)
  await page.goto('/login'); await page.getByPlaceholder('用户名', { exact: true }).fill('member'); await page.getByPlaceholder('密码', { exact: true }).fill('isolated-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '动态码或恢复码' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
  await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('999999'); await page.getByRole('button', { name: '验证并登录' }).click()
  await expect(page.getByRole('textbox', { name: '动态码或恢复码' })).toHaveValue('')
  await page.getByRole('textbox', { name: '动态码或恢复码' }).fill(codes[0]!); await page.getByRole('button', { name: '验证并登录' }).click()
  await expect(page).toHaveURL(/\/$/)
  expect(state.logins.at(-1)).toEqual({ username: 'member', password: 'isolated-password', otp_code: codes[0] })
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain('isolated-password')
})

test('取消双因素登录清掉密码与码，不复用旧认证输入', async ({ page }) => {
  await setup(page, false); await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('member'); await page.getByPlaceholder('密码', { exact: true }).fill('isolated-password'); await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('123456'); await page.getByRole('button', { name: '取消双因素登录' }).click()
  await expect(page.getByPlaceholder('密码', { exact: true })).toHaveValue('')
  await expect(page.getByRole('textbox', { name: '动态码或恢复码' })).toHaveCount(0)
})

test('手动密钥启用后一次展示恢复码，同步替换JWT而不卸载页面', async ({ page }, info) => {
  const state = await setup(page); await page.goto('/settings/two-factor'); await enable(page)
  expect(state.writes.map(item => item.body)).toEqual([{ current_password: 'isolated-password' }, { current_password: 'isolated-password', otp_code: '123456' }])
  await expect(page.getByText(codes[0]!, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '完成并清除恢复码' })).toBeDisabled()
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))
  expect(storage).not.toContain(seed); expect(storage).not.toContain(codes[0]); expect(storage).not.toContain('isolated-password')
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBe(jwt('security-2'))
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('totp-recovery-codes.png'), fullPage: true })
  await page.getByText('我已保存恢复码', { exact: true }).click(); await page.getByRole('button', { name: '完成并清除恢复码' }).click()
  await expect(page.getByText(codes[0]!, { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '重新生成恢复码' })).toBeVisible()
})

test('未保存恢复码离开需确认，取消保留，确认后清除', async ({ page }) => {
  await setup(page); await page.goto('/settings/two-factor'); await enable(page); await settingsLink(page)
  await expect(page.getByRole('dialog')).toContainText('未保存的恢复码将清除')
  await page.getByRole('button', { name: '取消', exact: true }).click(); await expect(page.getByText(codes[0]!, { exact: true })).toBeVisible()
  await settingsLink(page); await page.getByRole('button', { name: '确定', exact: true }).click(); await expect(page).toHaveURL(/\/settings$/)
  await page.goto('/settings/two-factor'); await expect(page.getByText(codes[0]!, { exact: true })).toHaveCount(0)
})

test('密钥设置过期清种子，取消重新生成；写中禁止重复与取消', async ({ page }) => {
  await page.clock.install(); const state = await setup(page); state.setupExpires = 1
  await page.goto('/settings/two-factor'); await start(page)
  expect(await page.evaluate(() => { const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); return event.defaultPrevented })).toBe(true)
  await page.clock.fastForward(2000)
  await expect(page.getByText('设置已过期，请取消后重新生成密钥。')).toBeVisible(); await expect(page.getByText(seed, { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '确认启用双因素认证' })).toBeDisabled(); await page.getByRole('button', { name: '取消', exact: true }).click()
  let release!: () => void; state.hold = new Promise<void>(resolve => { release = resolve }); state.setupExpires = 600
  await page.getByRole('textbox', { name: '当前密码', exact: true }).fill('isolated-password'); const generate = page.getByRole('button', { name: '生成认证器密钥' }); await generate.click()
  await expect(generate).toBeDisabled(); await expect(page.getByRole('button', { name: '取消', exact: true })).toBeDisabled(); await generate.evaluate((item: HTMLButtonElement) => item.click())
  expect(state.writes).toHaveLength(2); release(); await expect(page.getByText(seed, { exact: true })).toBeVisible()
})

test('已启用再生和停用均要双重证明，取消不发送，失败清输入', async ({ page }) => {
  const state = await setup(page); state.enabled = true; await page.goto('/settings/two-factor')
  await page.getByRole('textbox', { name: '当前密码', exact: true }).fill('isolated-password'); await page.getByRole('textbox', { name: '动态码或恢复码' }).fill(codes[0]!); await page.getByRole('button', { name: '重新生成恢复码' }).click()
  await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click(); expect(state.writes).toHaveLength(0)
  await page.getByRole('textbox', { name: '当前密码', exact: true }).fill('isolated-password'); await page.getByRole('textbox', { name: '动态码或恢复码' }).fill(codes[0]!); await page.getByRole('button', { name: '重新生成恢复码' }).click()
  await page.getByRole('dialog').getByRole('button', { name: '确定', exact: true }).click(); await expect(page.getByRole('heading', { name: '保存一次性恢复码' })).toBeVisible()
  expect(state.writes[0]).toEqual({ path: '/api/v1/auth/totp/recovery-codes/', body: { current_password: 'isolated-password', otp_code: codes[0] } })
  await page.getByText('我已保存恢复码', { exact: true }).click(); await page.getByRole('button', { name: '完成并清除恢复码' }).click()
  state.fail = true; await page.getByRole('textbox', { name: '当前密码', exact: true }).fill('isolated-password'); await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('123456'); await page.getByRole('button', { name: '停用双因素认证' }).click(); await page.getByRole('dialog').getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '安全修改未确认' })).toBeVisible(); await expect(page.getByRole('textbox', { name: '当前密码', exact: true })).toHaveValue('')
  state.fail = false; await page.getByRole('textbox', { name: '当前密码', exact: true }).fill('isolated-password'); await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('123456'); await page.getByRole('button', { name: '停用双因素认证' }).click(); await page.getByRole('dialog').getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText('未启用', { exact: true })).toBeVisible(); await expect(page.getByRole('button', { name: '生成认证器密钥' })).toBeVisible()
})

test('无密钥配置状态不可用，加载失败可刷新，旧登录晚响应不展示种子', async ({ page }) => {
  const state = await setup(page); state.available = false; await page.goto('/settings/two-factor')
  await expect(page.getByText('双因素认证暂不可用，请联系管理员完成安全配置。')).toBeVisible(); await expect(page.getByRole('button', { name: '生成认证器密钥' })).toHaveCount(0)
  state.available = true; state.statusFail = true; await page.getByRole('button', { name: '刷新', exact: true }).click(); await expect(page.getByRole('alert').filter({ hasText: '状态加载失败' })).toBeVisible()
  state.statusFail = false; await page.getByRole('button', { name: '刷新', exact: true }).click()
  let release!: () => void; state.hold = new Promise<void>(resolve => { release = resolve })
  await page.getByRole('textbox', { name: '当前密码', exact: true }).fill('isolated-password'); await page.getByRole('button', { name: '生成认证器密钥' }).click()
  await page.evaluate(access => localStorage.setItem('token', access), jwt('replacement')); release()
  await expect.poll(() => state.writes.length).toBe(1)
  await expect(page.getByRole('button', { name: '生成认证器密钥' })).toBeDisabled()
  await expect(page.getByText(seed, { exact: true })).toHaveCount(0)
})

test('英语手动设置支持移动布局', async ({ page }, info) => {
  await setup(page, true, true); await page.goto('/settings/two-factor')
  await page.getByRole('textbox', { name: 'Current Password', exact: true }).fill('isolated-password'); await page.getByRole('button', { name: 'Generate Authenticator Key' }).click()
  await expect(page.getByText(seed, { exact: true })).toBeVisible(); await expect(page.getByRole('button', { name: 'Copy Authenticator URI' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('totp-english.png'), fullPage: true })
})

test('跨标签会话切换清除种子和恢复码，同会话access轮换保留设置', async ({ page }) => {
  await setup(page); await page.goto('/settings/two-factor'); await start(page)
  await page.evaluate(() => {
    const previous = localStorage.getItem('token')
    window.dispatchEvent(new StorageEvent('storage', { key: 'token', oldValue: previous, newValue: previous }))
  })
  await expect(page.getByText(seed, { exact: true })).toBeVisible()
  await page.evaluate(access => {
    const previous = localStorage.getItem('token'); localStorage.setItem('token', access)
    window.dispatchEvent(new StorageEvent('storage', { key: 'token', oldValue: previous, newValue: access }))
  }, jwt('other-tab'))
  await expect(page.getByText(seed, { exact: true })).toHaveCount(0)
  await expect(page).not.toHaveURL(/\/settings\/two-factor$/)
  await page.goto('/settings/two-factor')
  await expect(page.getByRole('button', { name: '生成认证器密钥' })).toBeVisible()
  await enable(page)
  await page.evaluate(access => {
    const previous = localStorage.getItem('token'); localStorage.setItem('token', access)
    window.dispatchEvent(new StorageEvent('storage', { key: 'token', oldValue: previous, newValue: access }))
  }, jwt('another-tab'))
  await expect(page.getByText(codes[0]!, { exact: true })).toHaveCount(0)
})

test('动态码登录明确区分服务不可用与限流', async ({ page }) => {
  const state = await setup(page, false); await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('member'); await page.getByPlaceholder('密码', { exact: true }).fill('isolated-password'); await page.getByRole('button', { name: '登录', exact: true }).click()
  state.loginStatus = 503; await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('123456'); await page.getByRole('button', { name: '验证并登录' }).click()
  await expect(page.getByRole('alert').filter({ hasText: '服务暂不可用' })).toBeVisible()
  state.loginStatus = 429; await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('123456'); await page.getByRole('button', { name: '验证并登录' }).click()
  await expect(page.getByRole('alert').filter({ hasText: '尝试过于频繁' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
})
