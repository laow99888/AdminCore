import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const stamp = '2026-10-14T04:00:00Z'
async function setup(page: Page, english = false) {
  const state = { permissions: ['*'], member: false, empty: false, fail: false, failRevoke: false,
    requests: [] as string[], revokes: [] as { path: string; body: unknown; method: string }[],
    removed: false, hold: undefined as Promise<void> | undefined }
  await page.addInitScript(english => {
    localStorage.setItem('token', 'isolated-session-fixture')
    localStorage.setItem('refreshToken', 'isolated-refresh-fixture')
    if (english) { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') }
  }, english)
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'admin-id', username: 'admin', is_staff: !state.member, permissions: state.permissions }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/auth/sessions/') || path.endsWith('/auth/online-users/')) {
      state.requests.push(url.search)
      const admin = path.endsWith('/online-users/'), pageNumber = Number(url.searchParams.get('page') || 1)
      const sessions = [{ id: 'current-session', created_at: stamp, last_seen_at: stamp, expires_at: stamp, ip_address: '127.0.0.1', user_agent: 'Fixture current browser', is_current: true, active: true },
        { id: 'other-session', created_at: stamp, last_seen_at: stamp, expires_at: stamp, ip_address: null, user_agent: '<script>fixture-untrusted-device</script>', is_current: false, active: true }]
      const users = [{ id: 'admin-id', username: 'admin', first_name: '', last_name: '', session_count: 1, last_seen_at: stamp, is_current_user: true },
        { id: 'member-id', username: 'member', first_name: '', last_name: '', session_count: 2, last_seen_at: stamp, is_current_user: false }]
      const items = state.empty ? [] : pageNumber > 1 ? [{ ...sessions[1], user_agent: 'Second page device' }] : (admin ? users : sessions).filter(row => !state.removed || row.id === (admin ? 'admin-id' : 'current-session'))
      return route.fulfill({ status: state.fail ? 503 : 200, json: envelope({ items, pagination: { page: pageNumber, page_size: 10, total: state.empty ? 0 : 12, total_pages: 2 } }) })
    }
    if (path.includes('/auth/sessions/') || path.endsWith('/revoke/')) {
      state.revokes.push({ path, body: route.request().postDataJSON(), method: route.request().method() })
      if (state.hold) await state.hold
      if (!state.failRevoke) state.removed = true
      return route.fulfill({ status: state.failRevoke ? 400 : 200, json: envelope({ revoked_count: 1 }) })
    }
    return route.fulfill({ json: envelope({}) })
  })
  return state
}
const dialog = (page: Page) => page.getByRole('dialog')
const password = (page: Page) => dialog(page).getByRole('textbox', { name: '当前密码' })
const otherDevice = (page: Page) => page.getByRole('row').filter({ hasText: 'fixture-untrusted-device' }).getByRole('button', { name: '下线设备' })

test('本人设备按分页加载，取消不发送密码，下线只发送明确设备', async ({ page }, info) => {
  const state = await setup(page)
  await page.goto('/settings/sessions')
  await expect(page.getByRole('heading', { name: '会话与设备' })).toBeVisible()
  await expect(page.getByText('<script>fixture-untrusted-device</script>', { exact: true })).toBeVisible()
  await otherDevice(page).click()
  await password(page).fill('isolated-password')
  await dialog(page).getByRole('button', { name: '取消', exact: true }).click()
  expect(state.revokes).toHaveLength(0)
  await otherDevice(page).click()
  await expect(password(page)).toHaveValue('')
  await password(page).fill('isolated-password')
  await dialog(page).getByRole('button', { name: '确认下线' }).click()
  await expect(page.getByRole('status').filter({ hasText: '所选会话已下线' })).toBeVisible()
  expect(state.revokes).toEqual([{ path: '/api/v1/auth/sessions/other-session/', method: 'DELETE', body: { current_password: 'isolated-password' } }])
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('isolated-password'))).toBe(false)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('sessions.png'), fullPage: true })
})

test('失败立即清密码，重新输入才能重试，提交中阻止重复和关闭', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/settings/sessions')
  await otherDevice(page).click()
  state.failRevoke = true
  await password(page).fill('isolated-wrong-password')
  await dialog(page).getByRole('button', { name: '确认下线' }).click()
  await expect(dialog(page).getByRole('alert')).toContainText('下线未确认')
  await expect(password(page)).toHaveValue('')
  const confirm = dialog(page).getByRole('button', { name: '确认下线' })
  await expect(confirm).toBeDisabled()
  state.failRevoke = false
  let release!: () => void
  state.hold = new Promise<void>(resolve => { release = resolve })
  await password(page).fill('isolated-password')
  await confirm.click()
  await expect(confirm).toBeDisabled()
  await expect(password(page)).toHaveValue('')
  await expect(dialog(page).getByRole('button', { name: '取消', exact: true })).toBeDisabled()
  await confirm.evaluate((button: HTMLButtonElement) => button.click())
  await page.keyboard.press('Escape')
  await expect(dialog(page)).toBeVisible()
  expect(state.revokes).toHaveLength(2)
  release()
  await expect(dialog(page)).toHaveCount(0)
})

test('当前设备明确提示重新登录并清除两种凭据', async ({ page }) => {
  await setup(page)
  await page.goto('/settings/sessions')
  await page.getByRole('row').filter({ hasText: 'Fixture current browser' }).getByRole('button', { name: '下线设备' }).click()
  await expect(dialog(page)).toContainText('完成后需要重新登录')
  await password(page).fill('isolated-password')
  await dialog(page).getByRole('button', { name: '确认下线' }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => [localStorage.getItem('token'), localStorage.getItem('refreshToken')])).toEqual([null, null])
})

test('管理员搜索并仅撤销选定用户，自己的按钮禁用', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/system/online-users')
  await expect(page.getByRole('row').filter({ hasText: 'admin' }).getByRole('button', { name: '全部设备下线' })).toBeDisabled()
  await page.getByRole('textbox', { name: '搜索用户名' }).fill('member')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect.poll(() => state.requests.at(-1)).toContain('search=member')
  await page.getByRole('row').filter({ hasText: 'member' }).getByRole('button', { name: '全部设备下线' }).click()
  await expect(dialog(page)).toContainText('member 的全部设备下线')
  await password(page).fill('isolated-password')
  await dialog(page).getByRole('button', { name: '确认下线' }).click()
  await expect(dialog(page)).toHaveCount(0)
  expect(state.revokes).toEqual([{ path: '/api/v1/auth/online-users/member-id/revoke/', method: 'POST', body: { current_password: 'isolated-password' } }])
})

test('只读权限不呈现撤销按钮，普通成员不能进入管理页面', async ({ page }) => {
  const state = await setup(page)
  state.permissions = ['session:read']
  await page.goto('/system/online-users')
  await expect(page.getByRole('heading', { name: '在线用户' })).toBeVisible()
  await expect(page.getByRole('button', { name: '全部设备下线' })).toHaveCount(0)
  state.member = true
  await page.reload()
  await expect(page).toHaveURL(/\/403$/)
  expect(state.revokes).toHaveLength(0)
})

test('分页使用后端页码，加载失败不显示旧会话，空态可恢复', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/settings/sessions')
  await page.locator('.btn-next').click()
  await expect(page.getByText('Second page device', { exact: true })).toBeVisible()
  expect(state.requests.at(-1)).toContain('page=2')
  state.fail = true
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '有效会话加载失败' })).toBeVisible()
  await expect(page.getByRole('button', { name: '下线设备' })).toHaveCount(0)
  state.fail = false; state.empty = true
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByText('暂无数据', { exact: true })).toBeVisible()
  await expect(page.locator('.table-pagination')).toHaveCount(0)
})

test('英语深色模式提供设备与密码确认文案', async ({ page }, info) => {
  await setup(page, true)
  await page.goto('/settings/sessions')
  await expect(page.getByRole('heading', { name: 'Sessions & Devices' })).toBeVisible()
  await page.getByRole('row').filter({ hasText: 'fixture-untrusted-device' }).getByRole('button', { name: 'Sign Out Device' }).click()
  await expect(dialog(page)).toContainText('Password Confirmation')
  await expect(dialog(page).getByRole('textbox', { name: 'Current Password' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('sessions-english-dark.png'), fullPage: true })
})

test('两个标签页同时过期仅轮换一次 refresh，均恢复会话列表', async ({ context, page }) => {
  const jwt = (marker: string) => `fixture.${Buffer.from(JSON.stringify({ sid: 'shared-browser-session', user_id: 'member', session_version: 1, marker })).toString('base64url')}.fixture`
  const oldAccess = jwt('old'), newAccess = jwt('new'), oldRefresh = jwt('refresh-old'), newRefresh = jwt('refresh-new')
  let refreshes = 0
  await context.addInitScript(({ oldAccess, oldRefresh }) => {
    if (!localStorage.getItem('token')) { localStorage.setItem('token', oldAccess); localStorage.setItem('refreshToken', oldRefresh) }
  }, { oldAccess, oldRefresh })
  await context.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'member', username: 'member', is_staff: false, permissions: [] }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/auth/refresh/')) {
      refreshes++
      expect(route.request().postDataJSON()).toEqual({ refresh: oldRefresh })
      return route.fulfill({ status: refreshes === 1 ? 200 : 401, json: envelope({ access: newAccess, refresh: newRefresh }) })
    }
    if (path.endsWith('/auth/sessions/')) {
      if (route.request().headers().authorization !== `Bearer ${newAccess}`) return route.fulfill({ status: 401, json: { message: 'expired' } })
      return route.fulfill({ json: envelope({ items: [], pagination: { page: 1, page_size: 10, total: 0, total_pages: 0 } }) })
    }
    return route.fulfill({ json: envelope({}) })
  })
  const second = await context.newPage()
  await Promise.all([page.goto('/settings/sessions'), second.goto('/settings/sessions')])
  await expect(page.getByText('暂无数据', { exact: true })).toBeVisible()
  await expect(second.getByText('暂无数据', { exact: true })).toBeVisible()
  expect(refreshes).toBe(1)
  expect(await page.evaluate(() => localStorage.getItem('refreshToken'))).toBe(newRefresh)
  await second.close()
})
