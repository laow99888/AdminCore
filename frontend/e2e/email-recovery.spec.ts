import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const code = 'a'.repeat(32) + '.' + 'b'.repeat(64)
async function setup(page: Page, authenticated = false, english = false) {
  const state = { enabled: true, configFail: false, failRequest: false, failReset: false, failVerify: false, conflict: false, passwordError: false, versionConflict: false,
    requests: [] as unknown[], resets: [] as unknown[], sends: [] as unknown[], confirms: [] as unknown[], saves: [] as Record<string, unknown>[], profileReads: 0,
    hold: undefined as Promise<void> | undefined,
    profile: { id: 'member', username: 'member', email: 'm@example.com', first_name: '', last_name: '', phone: '', bio: '', avatar: '', profile_version: 1, has_avatar: false, avatar_enabled: false, email_verified: false, recovery_enabled: true, permissions: [] },
  }
  await page.addInitScript(({ authenticated, english }) => {
    if (authenticated) localStorage.setItem('token', 'isolated-verify-token')
    if (english) localStorage.setItem('language', 'en-US')
  }, { authenticated, english })
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (path.includes('/auth/recovery/')) expect(req.headers().authorization).toBeUndefined()
    if (path.endsWith('/auth/recovery/config/')) return route.fulfill({ status: state.configFail ? 503 : 200, json: envelope({ enabled: state.enabled }) })
    if (path.endsWith('/auth/recovery/request/')) {
      state.requests.push(req.postDataJSON()); if (state.hold) await state.hold
      return route.fulfill({ status: state.failRequest ? 503 : 202, json: envelope(null) })
    }
    if (path.endsWith('/auth/recovery/reset/')) {
      state.resets.push(req.postDataJSON()); if (state.hold) await state.hold
      return route.fulfill({ status: state.failReset || state.passwordError ? 400 : 200, json: state.passwordError ? { code: 400, message: '参数验证失败', data: { new_password: ['新密码不能与当前密码相同'] } } : envelope(null) })
    }
    if (path.endsWith('/auth/email-verification/request/')) {
      state.sends.push(req.postDataJSON()); if (state.hold) await state.hold
      return route.fulfill({ status: state.failVerify ? 400 : 202, json: envelope(null) })
    }
    if (path.endsWith('/auth/email-verification/confirm/')) {
      state.confirms.push(req.postDataJSON()); if (state.hold) await state.hold
      if (state.failVerify) return route.fulfill({ status: 400, json: envelope(null) })
      state.profile = { ...state.profile, email_verified: true, profile_version: state.profile.profile_version + (state.versionConflict ? 2 : 1), last_name: state.versionConflict ? 'changed-in-other-window' : state.profile.last_name, email: state.conflict ? 'other@example.com' : state.profile.email }
      return route.fulfill({ json: envelope(state.profile) })
    }
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope(state.profile) })
    if (path.endsWith('/auth/profile/')) {
      if (req.method() === 'PATCH') {
        state.saves.push(req.postDataJSON())
        state.profile = { ...state.profile, ...req.postDataJSON(), email_verified: false, profile_version: state.profile.profile_version + 1 }
      } else state.profileReads++
      return route.fulfill({ json: envelope(state.profile) })
    }
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: '现代化中后台管理系统' }) })
    return route.fulfill({ json: envelope({}) })
  })
  return state
}
const secretStorage = (page: Page) => page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))
async function fillReset(page: Page) {
  await page.getByRole('button', { name: '已有邮件代码', exact: true }).click()
  await page.getByRole('textbox', { name: '邮件代码', exact: true }).fill(code)
  await page.getByRole('textbox', { name: '新密码', exact: true }).fill('isolated-new-password')
  await page.getByRole('textbox', { name: '确认新密码', exact: true }).fill('isolated-new-password')
}

test('登录入口按配置显示，公开恢复申请与确认不自动登录、不存敏感信息', async ({ page }, info) => {
  const state = await setup(page)
  await page.goto('/login')
  await page.getByRole('button', { name: '忘记密码', exact: true }).click()
  await expect(page.getByRole('heading', { name: '找回密码', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '用户名', exact: true }).fill('member')
  await page.getByRole('textbox', { name: '已验证邮箱', exact: true }).fill('m@example.com')
  await page.getByRole('button', { name: '提交找回申请' }).click()
  await expect(page.getByRole('status').filter({ hasText: '若账号与已验证邮箱匹配' })).toBeVisible()
  expect(state.requests).toEqual([{ username: 'member', email: 'm@example.com' }])
  await fillReset(page)
  await page.getByRole('button', { name: '重置密码', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '密码已重置，请返回登录' })).toBeVisible()
  expect(state.resets).toEqual([{ code, new_password: 'isolated-new-password', new_password2: 'isolated-new-password' }])
  expect(await secretStorage(page)).not.toContain(code)
  expect(await secretStorage(page)).not.toContain('isolated-new-password')
  expect(page.url()).not.toContain(code)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('recovery.png'), fullPage: true })
})

test('关闭配置隐藏忘记密码，直接页面给禁用说明；配置失败可重试', async ({ page }) => {
  const state = await setup(page); state.enabled = false
  await page.goto('/login')
  await expect(page.getByText('邮件找回未启用，请联系管理员重置密码。', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '忘记密码' })).toHaveCount(0)
  await page.goto('/recover-password')
  await expect(page.getByRole('button', { name: '提交找回申请' })).toHaveCount(0)
  state.enabled = true; state.configFail = true
  await page.reload()
  await expect(page.getByRole('alert')).toContainText('找回密码配置加载失败')
  state.configFail = false
  await page.getByRole('button', { name: '重试找回配置' }).click()
  await expect(page.getByRole('button', { name: '提交找回申请' })).toBeVisible()
})

test('失败允许重输，空值禁用，重复提交和取消受保护', async ({ page }) => {
  const state = await setup(page); state.failReset = true
  await page.goto('/recover-password')
  await expect(page.getByRole('button', { name: '提交找回申请' })).toBeDisabled()
  await fillReset(page)
  await page.getByRole('button', { name: '重置密码', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('重置未确认')
  await expect(page.getByRole('textbox', { name: '邮件代码', exact: true })).toHaveValue('')
  await expect(page.getByRole('textbox', { name: '新密码', exact: true })).toHaveValue('')
  state.failReset = false
  let release!: () => void; state.hold = new Promise<void>(resolve => { release = resolve })
  await fillReset(page)
  const button = page.getByRole('button', { name: '重置密码', exact: true })
  await button.click(); await expect(button).toBeDisabled()
  await expect(page.getByRole('button', { name: '取消并返回登录' })).toBeDisabled()
  await button.evaluate((element: HTMLButtonElement) => element.click())
  expect(state.resets).toHaveLength(2)
  release(); await expect(button).toHaveCount(0)
})

test('公开恢复保留已有JWT且不发送认证头，取消清除代码和密码', async ({ page }) => {
  await setup(page, true)
  await page.goto('/recover-password')
  await fillReset(page)
  await page.getByRole('button', { name: '取消并返回登录' }).click()
  await expect(page).toHaveURL(/\/$/)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBe('isolated-verify-token')
  await page.goto('/recover-password')
  await page.getByRole('button', { name: '已有邮件代码', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '邮件代码', exact: true })).toHaveValue('')
})

test('邮箱只验证保存地址，密码提交清空，202准确提示排队，确认更新状态', async ({ page }, info) => {
  const state = await setup(page, true)
  await page.goto('/settings')
  await page.getByRole('textbox', { name: '邮箱', exact: true }).fill('changed@example.com')
  await expect(page.getByText('邮箱修改尚未保存；保存后需重新验证。')).toBeVisible()
  await expect(page.getByRole('button', { name: '申请邮箱验证' })).toHaveCount(0)
  await page.getByRole('textbox', { name: '邮箱', exact: true }).fill('m@example.com')
  await page.getByRole('textbox', { name: '邮箱验证当前密码' }).fill('isolated-current-password')
  await page.getByRole('button', { name: '申请邮箱验证' }).click()
  await expect(page.getByRole('status').filter({ hasText: '邮件由后台异步发送' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '邮箱验证当前密码' })).toHaveValue('')
  expect(state.sends).toEqual([{ current_password: 'isolated-current-password' }])
  await page.getByRole('textbox', { name: '邮箱验证代码' }).fill(code)
  await page.getByRole('button', { name: '确认邮箱验证' }).click()
  await expect(page.getByText('已验证', { exact: true })).toBeVisible()
  expect(state.confirms).toEqual([{ code }])
  expect(await secretStorage(page)).not.toContain(code)
  expect(await secretStorage(page)).not.toContain('isolated-current-password')
  await page.screenshot({ path: info.outputPath('email-verified.png'), fullPage: true })
})

test('验证失败保留资料草稿并清代码，冲突不给旧资料覆盖输入', async ({ page }) => {
  const state = await setup(page, true); state.failVerify = true
  await page.goto('/settings')
  await page.getByRole('textbox', { name: '名字', exact: true }).fill('unsaved-name')
  await page.getByRole('textbox', { name: '邮箱验证代码' }).fill(code)
  await page.getByRole('button', { name: '确认邮箱验证' }).click()
  await expect(page.getByRole('alert').filter({ hasText: '邮箱验证未确认' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '名字', exact: true })).toHaveValue('unsaved-name')
  await expect(page.getByRole('textbox', { name: '邮箱验证代码' })).toHaveValue('')
  state.failVerify = false; state.conflict = true
  await page.getByRole('textbox', { name: '邮箱验证代码' }).fill(code)
  await page.getByRole('button', { name: '确认邮箱验证' }).click()
  const panel = page.getByRole('region', { name: '编辑冲突', exact: true })
  await expect(panel).toBeVisible()
  await expect(page.getByRole('textbox', { name: '名字', exact: true })).toHaveValue('unsaved-name')
  await expect(page.getByRole('textbox', { name: '邮箱', exact: true })).toHaveValue('m@example.com')
  await expect(page.getByRole('textbox', { name: '邮箱验证代码' })).toHaveValue('')
  await expect(page.getByRole('button', { name: '保存资料' })).toBeDisabled()
  expect(state.profileReads).toBe(1); expect(state.saves).toHaveLength(0)
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.locator('tbody tr')).toHaveCount(5)
  await expect(panel.getByRole('row').filter({ has: page.getByRole('rowheader', { name: '邮箱', exact: true }) })).toContainText('other@example.com')
  await expect(page.getByRole('textbox', { name: '名字', exact: true })).toHaveValue('unsaved-name')
  await expect(page.getByRole('textbox', { name: '邮箱', exact: true })).toHaveValue('m@example.com')
  await expect(page.getByRole('button', { name: '保存资料' })).toBeDisabled()
  await panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click()
  await expect(panel).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: '名字', exact: true })).toHaveValue('')
  await expect(page.getByRole('textbox', { name: '邮箱', exact: true })).toHaveValue('other@example.com')
  await expect(page.getByText('已验证', { exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '名字', exact: true }).fill('reviewed-name')
  await page.getByRole('button', { name: '保存资料' }).click()
  await expect.poll(() => state.saves).toEqual([{ first_name: 'reviewed-name', last_name: '', email: 'other@example.com', phone: '', bio: '', profile_version: 2 }])
  expect(await secretStorage(page)).not.toContain(code)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('保存邮箱更改使验证失效，空邮箱和禁用邮件无验证表单', async ({ page }) => {
  const state = await setup(page, true); state.profile.email_verified = true
  await page.goto('/settings')
  await expect(page.getByText('已验证', { exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '邮箱', exact: true }).fill('new@example.com')
  await page.getByRole('button', { name: '保存资料' }).click()
  await expect(page.getByText('未验证', { exact: true })).toBeVisible()
  await expect(page.getByText('验证邮件只发送到已保存邮箱：new@example.com')).toBeVisible()
  state.profile.email = ''; await page.reload()
  await expect(page.getByText('请先保存非空邮箱，再申请验证。')).toBeVisible()
  await expect(page.getByRole('button', { name: '申请邮箱验证' })).toHaveCount(0)
  state.profile.email = 'm@example.com'; state.profile.recovery_enabled = false; await page.reload()
  await expect(page.getByRole('button', { name: '申请邮箱验证' })).toHaveCount(0)
})

test('英文移动恢复页与验证提示可读且不溢出', async ({ page }, info) => {
  await setup(page, false, true)
  await page.goto('/recover-password')
  await expect(page.getByRole('heading', { name: 'Recover Password' })).toBeVisible()
  await page.getByRole('button', { name: 'I Have an Email Code' }).click()
  await expect(page.getByRole('textbox', { name: 'Email Code', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('recovery-english.png'), fullPage: true })
})

test('重置明确显示安全密码字段错误，不自动跳转或恢复敏感输入', async ({ page }) => {
  const state = await setup(page); state.passwordError = true
  await page.goto('/recover-password'); await fillReset(page)
  await page.getByRole('button', { name: '重置密码', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('新密码不能与当前密码相同')
  await expect(page.getByRole('textbox', { name: '邮件代码', exact: true })).toHaveValue('')
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
})

test('邮箱验证晚响应遇到登录会话切换不更新旧资料', async ({ page }) => {
  const state = await setup(page, true)
  let release!: () => void; state.hold = new Promise<void>(resolve => { release = resolve })
  await page.goto('/settings')
  await page.getByRole('textbox', { name: '邮箱验证代码' }).fill(code)
  const confirm = page.getByRole('button', { name: '确认邮箱验证' })
  await confirm.click(); await expect(confirm).toBeDisabled()
  await expect(page.getByRole('textbox', { name: '邮箱验证代码' })).toHaveValue('')
  await page.evaluate(() => localStorage.setItem('token', 'replacement-token'))
  release()
  await expect.poll(() => state.profile.email_verified).toBe(true)
  await expect(confirm).toBeDisabled()
  await expect(page.getByText('未验证', { exact: true })).toBeVisible()
  await expect(page.getByText('已验证', { exact: true })).toHaveCount(0)
  expect(await secretStorage(page)).not.toContain(code)
})

test('另一窗口先改资料再验证时，版本跳跃会保护当前草稿免于覆盖', async ({ page }) => {
  const state = await setup(page, true); state.versionConflict = true
  await page.goto('/settings')
  await page.getByRole('textbox', { name: '个人简介' }).fill('unsaved-local-bio')
  await page.getByRole('textbox', { name: '邮箱验证代码' }).fill(code)
  await page.getByRole('button', { name: '确认邮箱验证' }).click()
  const panel = page.getByRole('region', { name: '编辑冲突', exact: true })
  await expect(panel).toBeVisible()
  await expect(page.getByRole('textbox', { name: '个人简介' })).toHaveValue('unsaved-local-bio')
  await expect(page.getByRole('textbox', { name: '姓氏', exact: true })).toHaveValue('')
  await expect(page.getByRole('button', { name: '保存资料' })).toBeDisabled()
  expect(state.profile.last_name).toBe('changed-in-other-window')
  expect(state.profileReads).toBe(1); expect(state.saves).toHaveLength(0)
  await expect(page.getByRole('textbox', { name: '邮箱验证代码' })).toHaveValue('')
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.locator('tbody tr')).toHaveCount(5)
  await expect(panel).toContainText('当前编辑版本：1；服务器版本：3')
  await expect(panel.getByRole('row').filter({ has: page.getByRole('rowheader', { name: '姓氏', exact: true }) })).toContainText('changed-in-other-window')
  await expect(panel.getByRole('row').filter({ has: page.getByRole('rowheader', { name: '个人简介', exact: true }) })).toContainText('unsaved-local-bio')
  await expect(page.getByRole('textbox', { name: '个人简介' })).toHaveValue('unsaved-local-bio')
  await expect(page.getByRole('textbox', { name: '姓氏', exact: true })).toHaveValue('')
  await expect(page.getByRole('button', { name: '保存资料' })).toBeDisabled()
  await panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click()
  await expect(panel).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: '姓氏', exact: true })).toHaveValue('changed-in-other-window')
  await expect(page.getByRole('textbox', { name: '个人简介' })).toHaveValue('')
  await expect(page.getByText('已验证', { exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '个人简介' }).fill('reviewed-bio')
  await page.getByRole('button', { name: '保存资料' }).click()
  await expect.poll(() => state.saves).toEqual([{ first_name: '', last_name: 'changed-in-other-window', email: 'm@example.com', phone: '', bio: 'reviewed-bio', profile_version: 3 }])
  expect(await secretStorage(page)).not.toContain(code)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
