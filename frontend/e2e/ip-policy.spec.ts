import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, mode: 'write' | 'read' | 'off' = 'write') {
  const policy = { enabled: false, allow: ['127.0.0.1/32'], deny: [], version: 1, updated_at: '' }
  const state = { mode, fail: false, conflict: false, reads: 0, previews: 0, saves: [] as Record<string, unknown>[] }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-ip-policy-fixture'))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'owner', username: 'owner', permissions: state.mode === 'write' ? ['ip_policy:read', 'ip_policy:update'] : ['ip_policy:read'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'ip_policy', title: 'IP 访问策略', enabled: state.mode !== 'off', dependencies: [], paths: ['/system/ip-policy'], page_permissions: { '/system/ip-policy': 'ip_policy:read' } }] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'menu', name: 'IP 访问策略', path: '/system/ip-policy', icon: 'settings', children: [] }]) })
    if (path.endsWith('/ip-policy/preview/')) { state.previews++; return route.fulfill({ json: envelope({ source_ip: '127.0.0.1', allowed: true }) }) }
    if (path.endsWith('/ip-policy/')) {
      if (method === 'PUT') {
        state.saves.push(route.request().postDataJSON())
        if (state.conflict) return route.fulfill({ status: 409, json: { code: 409, message: '记录已变化', data: null } })
        return route.fulfill({ json: envelope({ ...policy, version: 2 }) })
      }
      state.reads++
      if (state.fail) return route.fulfill({ status: 503, json: { code: 503, message: 'fixture unavailable', data: null } })
      return route.fulfill({ json: envelope(state.conflict && state.reads > 1 ? { ...policy, allow: ['::1/128'], version: 2 } : policy) })
    }
    return route.fulfill({ json: envelope({}) })
  })
  return state
}

test('只读策略和手机布局', async ({ page }, info) => {
  await setup(page, 'read'); await page.goto('/system/ip-policy')
  await expect(page.getByRole('textbox', { name: '允许网络', exact: true })).toHaveValue('127.0.0.1/32')
  await expect(page.getByRole('textbox', { name: '允许网络', exact: true })).toBeDisabled()
  await expect(page.getByRole('switch', { name: '启用 IP 策略', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '保存', exact: true })).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: '当前密码', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '预检当前来源', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '允许访问' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('ip-policy-read.png'), fullPage: true, animations: 'disabled' })
})

test('预检、编辑失效、密码确认及保存后清空', async ({ page }, info) => {
  const state = await setup(page); await page.goto('/system/ip-policy')
  const allow = page.getByRole('textbox', { name: '允许网络', exact: true }), password = page.getByRole('textbox', { name: '当前密码', exact: true }), save = page.getByRole('button', { name: '保存', exact: true })
  await allow.fill('127.0.0.1\n::1')
  await password.fill('browser-fixture-password')
  await expect(save).toBeDisabled()
  await page.getByRole('button', { name: '预检当前来源', exact: true }).click()
  await expect(save).toBeEnabled()
  await allow.fill('127.0.0.1')
  await expect(save).toBeDisabled()
  await page.getByRole('button', { name: '预检当前来源', exact: true }).click()
  await expect(save).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('ip-policy-edit.png'), fullPage: true, animations: 'disabled' })
  await save.click()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0]).toEqual({ enabled: false, allow: ['127.0.0.1'], deny: [], version: 1, current_password: 'browser-fixture-password' })
  await expect(password).toHaveValue('')
  await expect(save).toBeDisabled()
})

test('并发冲突保留输入，应用服务器版本后重新预检', async ({ page }) => {
  const state = await setup(page); state.conflict = true; await page.goto('/system/ip-policy')
  const allow = page.getByRole('textbox', { name: '允许网络', exact: true }), password = page.getByRole('textbox', { name: '当前密码', exact: true }), save = page.getByRole('button', { name: '保存', exact: true })
  await allow.fill('127.0.0.1'); await password.fill('browser-fixture-password')
  await page.getByRole('button', { name: '预检当前来源', exact: true }).click(); await save.click()
  const panel = page.getByRole('region', { name: '编辑冲突' })
  await expect(panel).toBeVisible(); await expect(allow).toHaveValue('127.0.0.1'); await expect(password).toHaveValue('')
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.getByRole('table')).toContainText('::1/128'); await expect(allow).toHaveValue('127.0.0.1')
  await panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click()
  await expect(allow).toHaveValue('::1/128'); await expect(save).toBeDisabled()
  state.conflict = false; await password.fill('browser-fixture-password')
  await page.getByRole('button', { name: '预检当前来源', exact: true }).click(); await save.click()
  await expect.poll(() => state.saves.length).toBe(2)
  expect(state.saves[1].version).toBe(2)
})

test('加载失败可恢复，关闭模块不请求策略', async ({ page }) => {
  const state = await setup(page, 'off'); await page.goto('/system/ip-policy')
  await expect(page).toHaveURL('/'); expect(state.reads).toBe(0)
  state.mode = 'write'; state.fail = true; await page.reload(); await page.goto('/system/ip-policy')
  await expect(page.getByRole('alert').filter({ hasText: '加载失败，请重试' })).toBeVisible()
  state.fail = false; await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '允许网络', exact: true })).toHaveValue('127.0.0.1/32')
})
