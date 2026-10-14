import { expect, test, type Page } from '@playwright/test'
const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3XcAAAAASUVORK5CYII='
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, english = false) {
  const state = { gate: true, enabled: true, mfa: false, mfaCaptchaError: false, threshold: 0, logins: [] as Record<string, string>[], challenges: [] as string[], expires: 120, fail: false, invalidImage: false, decodeError: false, status: 0, network: false, hold: undefined as Promise<void> | undefined }
  const user = { id: 'captcha-user', username: 'member', email: '', avatar: '', permissions: ['*'], is_staff: true }
  await page.addInitScript(english => { localStorage.clear(); if (english) localStorage.setItem('language', 'en-US') }, english)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/login-captcha/')) {
      state.challenges.push(route.request().postDataJSON().username); const number = state.challenges.length
      if (state.hold) await state.hold
      if (state.fail) return route.fulfill({ status: 503, json: envelope(null) })
      return route.fulfill({ json: envelope(state.enabled ? { required: true, challenge_id: id(number), image: state.invalidImage ? 'data:image/svg+xml;base64,PHN2Zy8+' : state.decodeError ? 'data:image/png;base64,iVBORw0KGgo=' : image, expires_in: state.expires } : { required: false }) })
    }
    if (path.endsWith('/auth/login/')) {
      const body = route.request().postDataJSON(); state.logins.push(body)
      if (state.network) return route.abort('failed')
      if (state.status) return route.fulfill({ status: state.status, json: { code: state.status, message: 'service unavailable', data: null } })
      if (state.threshold && !body.captcha_id) return route.fulfill({ status: 401, json: { code: 401, message: '认证失败', data: state.logins.length >= state.threshold ? { code: 'captcha_required' } : null } })
      if (state.gate && !body.captcha_id) return route.fulfill({ status: 400, json: { code: 400, message: '验证失败', data: { code: 'captcha_required' } } })
      if (state.gate && body.captcha_code !== 'ABCDE') return route.fulfill({ status: 400, json: { code: 400, message: '验证失败', data: { code: 'captcha_invalid' } } })
      if (state.mfa && !body.otp_code) return route.fulfill({ status: 401, json: { code: 401, message: '认证失败', data: { code: 'mfa_required' } } })
      if (state.mfaCaptchaError) return route.fulfill({ status: 401, json: { code: 401, message: '认证失败', data: { code: 'captcha_required' } } })
      return route.fulfill({ json: { access: `fixture.${btoa(JSON.stringify({ sid: 'captcha-login', user_id: user.id, session_version: 1 }))}.fixture`, refresh: 'fixture-refresh', user } })
    }
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope(user) })
    if (path.endsWith('/auth/recovery/config/')) return route.fulfill({ json: envelope({ enabled: true }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: '现代化中后台管理系统' }) })
    return route.fulfill({ json: envelope({ items: [], count: 0, totals: {}, login_trend: [], task_status: {} }) })
  })
  return state
}
async function credentials(page: Page, english = false) { await page.getByPlaceholder(english ? 'Username' : '用户名', { exact: true }).fill('member'); await page.getByPlaceholder(english ? 'Password' : '密码', { exact: true }).fill('isolated-password') }
const input = (page: Page, english = false) => page.getByRole('textbox', { name: english ? 'Image Verification Code' : '图形验证码', exact: true })
const refresh = (page: Page, english = false) => page.getByRole('button', { name: english ? 'Refresh Security Image' : '刷新验证码', exact: true })
async function gate(page: Page) { await page.goto('/login'); await credentials(page); await page.getByRole('button', { name: '登录', exact: true }).click(); await expect(input(page)).toBeEnabled() }

test('首次正常提交后按服务端gate，单次captcha与密码明确提交成功清理', async ({ page }) => {
  const state = await setup(page); await gate(page)
  expect(state.logins).toEqual([{ username: 'member', password: 'isolated-password' }]); expect(state.challenges).toEqual(['member'])
  await expect(page.getByRole('img', { name: '登录验证码图片' })).toBeVisible()
  await input(page).fill('abcde'); await input(page).press('Enter'); await expect(page).toHaveURL(/\/$/)
  expect(state.logins.at(-1)).toEqual({ username: 'member', password: 'isolated-password', captcha_id: id(1), captcha_code: 'ABCDE' })
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toMatch(/isolated-password|captcha_id|captcha_code|data:image|ABCDE/)
})

test('第三次401凭据失败即展示captcha，不额外等待第四次提交', async ({ page }) => {
  const state = await setup(page); state.threshold = 3; await page.goto('/login'); await credentials(page)
  for (let attempt = 1; attempt <= 3; attempt++) {
    await page.getByRole('button', { name: '登录', exact: true }).click(); await expect.poll(() => state.logins.length).toBe(attempt)
    if (attempt < 3) { await expect(page.getByRole('button', { name: '登录', exact: true })).toBeEnabled(); await expect(input(page)).toHaveCount(0) }
  }
  await expect(input(page)).toBeEnabled(); expect(state.logins).toHaveLength(3); expect(state.challenges).toEqual(['member'])
})

test('错误已消费挑战和手动刷新都换id，输入清空，过期禁登录可重试', async ({ page }) => {
  const state = await setup(page); await page.clock.install(); await gate(page)
  await input(page).fill('WRONG'); await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect.poll(() => state.challenges.length).toBe(2); await expect(input(page)).toBeEnabled(); await expect(input(page)).toHaveValue('')
  await input(page).fill('ABCDE'); state.expires = 1; await refresh(page).click(); await expect.poll(() => state.challenges.length).toBe(3)
  await page.clock.fastForward(2000); await expect(page.getByText('验证码已过期，请刷新后重试。')).toBeVisible(); await expect(page.getByRole('button', { name: '登录', exact: true })).toBeDisabled()
  state.expires = 120; await refresh(page).click(); await expect(input(page)).toBeEnabled(); await input(page).fill('ABCDE'); await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/); expect(state.logins.at(-1)?.captcha_id).toBe(id(4))
})

test('验证码与TOTP串联，缺动态码后重取挑战，取消清密码和全部证明', async ({ page }) => {
  const state = await setup(page); state.mfa = true; await gate(page)
  await input(page).fill('ABCDE'); await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '动态码或恢复码' })).toBeVisible(); await expect.poll(() => state.challenges.length).toBe(2); await expect(input(page)).toBeEnabled()
  await expect(page.getByPlaceholder('用户名', { exact: true })).toBeDisabled(); await expect(input(page)).toHaveValue('')
  await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('123456'); await input(page).fill('ABCDE'); await page.getByRole('button', { name: '取消双因素登录' }).click()
  await expect(input(page)).toHaveCount(0); await expect(page.getByPlaceholder('密码', { exact: true })).toHaveValue('')
  await credentials(page); await page.getByRole('button', { name: '登录', exact: true }).click(); await expect(input(page)).toBeEnabled()
  await input(page).fill('ABCDE'); await page.getByRole('button', { name: '登录', exact: true }).click(); await expect.poll(() => state.challenges.length).toBe(4); await expect(input(page)).toBeEnabled()
  state.mfaCaptchaError = true; await input(page).fill('ABCDE'); await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('999999'); await page.getByRole('button', { name: '验证并登录' }).click()
  await expect.poll(() => state.challenges.length).toBe(5); await expect(input(page)).toBeEnabled(); await expect(page.getByRole('textbox', { name: '动态码或恢复码' })).toHaveValue('')
  state.mfaCaptchaError = false; await input(page).fill('ABCDE'); await page.getByRole('textbox', { name: '动态码或恢复码' }).fill('123456'); await page.getByRole('button', { name: '验证并登录' }).click()
  await expect(page).toHaveURL(/\/$/); expect(state.logins.at(-1)).toMatchObject({ otp_code: '123456', captcha_id: id(5), captcha_code: 'ABCDE' })
})

test('用户名切换取消旧challenge，晚响应不把旧图片带给新用户', async ({ page }) => {
  const state = await setup(page); let release!: () => void; state.hold = new Promise(resolve => { release = resolve })
  await page.goto('/login'); await credentials(page); await page.getByRole('button', { name: '登录', exact: true }).click(); await expect.poll(() => state.challenges.length).toBe(1)
  await page.getByPlaceholder('用户名', { exact: true }).fill('another'); await expect(input(page)).toHaveCount(0)
  release(); state.hold = undefined; await page.getByRole('button', { name: '登录', exact: true }).click(); await expect(input(page)).toBeEnabled()
  expect(state.challenges).toEqual(['member', 'another']); await input(page).fill('ABCDE'); await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/$/); expect(state.logins.at(-1)).toMatchObject({ username: 'another', captcha_id: id(2) })
})

test('异常PNG和加载错误禁登录，刷新重试与配置关闭清理gate', async ({ page }) => {
  const state = await setup(page); state.invalidImage = true; await page.goto('/login'); await credentials(page); await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('验证码加载失败，请刷新重试。')).toBeVisible(); await expect(page.getByRole('img', { name: '登录验证码图片' })).toHaveCount(0)
  state.invalidImage = false; state.decodeError = true; await refresh(page).click(); await expect(page.getByText('验证码图片无法显示，请刷新或联系管理员。')).toBeVisible()
  state.decodeError = false; state.fail = true; await refresh(page).click(); await expect.poll(() => state.challenges.length).toBe(3); await expect(page.getByText('验证码加载失败，请刷新重试。')).toBeVisible()
  state.fail = false; state.enabled = false; state.gate = false; await refresh(page).click(); await expect(input(page)).toHaveCount(0)
  await page.getByRole('button', { name: '登录', exact: true }).click(); await expect(page).toHaveURL(/\/$/); expect(state.logins.at(-1)).not.toHaveProperty('captcha_id')
})

test('网络不明与503429均清已提交challenge，区分服务错误可重新获取', async ({ page }) => {
  const state = await setup(page); await gate(page)
  for (const failure of ['network', 503, 429] as const) {
    const count = state.challenges.length; state.network = failure === 'network'; state.status = typeof failure === 'number' ? failure : 0
    await input(page).fill('ABCDE'); await page.getByRole('button', { name: '登录', exact: true }).click(); await expect.poll(() => state.challenges.length).toBe(count + 1)
    await expect(input(page)).toBeEnabled(); await expect(input(page)).toHaveValue('')
    await expect(page.getByText(failure === 'network' ? '登录未确认，请稍后重试。' : failure === 503 ? '登录服务暂不可用，请稍后重试或联系管理员。' : '尝试过于频繁，请稍后再试。', { exact: true }).last()).toBeVisible()
  }
})

test('默认关闭无额外captcha请求，未提交输入离开不持久化', async ({ page }) => {
  const state = await setup(page); state.gate = false; state.enabled = false; await page.goto('/login'); await credentials(page)
  expect(state.challenges).toHaveLength(0); await expect(input(page)).toHaveCount(0)
  await page.getByRole('button', { name: '忘记密码', exact: true }).click(); await expect(page).toHaveURL(/\/recover-password$/)
  await page.goto('/login'); await expect(page.getByPlaceholder('密码', { exact: true })).toHaveValue(''); await credentials(page)
  await page.getByRole('button', { name: '登录', exact: true }).click(); await expect(page).toHaveURL(/\/$/); expect(state.challenges).toHaveLength(0)
})

test('英语移动验证码与MFA可滚动，键盘输入与无横向溢出', async ({ page }) => {
  const state = await setup(page, true); state.mfa = true; await page.goto('/login'); await credentials(page, true); await page.getByRole('button', { name: 'Sign In', exact: true }).click(); await expect(input(page, true)).toBeEnabled()
  await input(page, true).fill('abcde'); await input(page, true).press('Enter'); await expect(page.getByRole('textbox', { name: 'Authenticator or Recovery Code' })).toBeVisible(); await expect(input(page, true)).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.getByText(/contact an administrator for help/)).toBeVisible(); await page.screenshot({ path: test.info().outputPath('login-captcha-english.png'), fullPage: true })
  await input(page, true).fill('ABCDE'); await page.getByRole('textbox', { name: 'Authenticator or Recovery Code' }).fill('123456'); await page.getByRole('button', { name: 'Verify & Sign In' }).click(); await expect(page).toHaveURL(/\/$/)
})
