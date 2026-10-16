import { test, expect, type Page } from '@playwright/test'

const stamp = '20261016-010203'
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, mode: 'write' | 'read' | 'offline' = 'write') {
  const state = { mode, fail: false, previews: 0, saves: [] as Record<string, unknown>[] }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-backups-fixture'))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'owner', username: 'owner', is_staff: true, permissions: state.mode === 'read' ? ['backup:read'] : ['backup:read', 'backup:restore'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'tasks', title: '任务', enabled: true, dependencies: [], paths: ['/tasks', '/tasks/backups'], page_permissions: { '/tasks/backups': 'backup:read' } }] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'menu', name: '备份与恢复', path: '/tasks/backups', icon: 'database-backup', children: [] }]) })
    if (path.endsWith('/preflight/')) {
      state.previews++
      if (state.fail) return route.fulfill({ status: 400, json: { code: 400, message: 'fixture failed', data: null } })
      return route.fulfill({ json: envelope({ preflight_id: 'fixture-preflight', timestamp: stamp, remote_copy: true, artifacts: [] }) })
    }
    if (path.endsWith('/restore/')) {
      state.saves.push(route.request().postDataJSON())
      return route.fulfill({ status: 202, json: envelope({ id: 'restore', status: 'pending' }) })
    }
    if (path.endsWith('/tasks/backups/')) return route.fulfill({ json: envelope({ enabled: true, state: state.mode === 'offline' ? 'offline' : 'idle', directory_label: 'private-backups', stage: '', last_error: '', last_seen_at: '2026-10-16T01:02:03Z', artifacts: [{ timestamp: stamp, created_at: '2026-10-16T01:02:03Z', artifacts: [{}, {}, {}], remote_copy: true }], restore_requests: state.saves.length ? [{ id: 'restore', timestamp: stamp, status: 'pending', error: '', created_at: '', completed_at: null }] : [] }) })
    return route.fulfill({ json: envelope({}) })
  })
  return state
}

test('恢复预检、密码和确认文本，桌面及手机没有页面溢出', async ({ page }, info) => {
  const state = await setup(page); await page.goto('/tasks/backups')
  await page.getByRole('button', { name: '预检恢复', exact: true }).click()
  await page.getByRole('button', { name: '运行预检', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '恢复备份' })
  const submit = dialog.getByRole('button', { name: '确认登记恢复', exact: true })
  await expect(submit).toBeDisabled()
  await dialog.getByRole('textbox', { name: '当前密码', exact: true }).fill('browser-fixture-password')
  await dialog.getByRole('textbox', { name: '确认文本', exact: true }).fill('恢复备份')
  await expect(submit).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('backups-confirm.png'), fullPage: true, animations: 'disabled' })
  await submit.click(); await expect(dialog).not.toBeVisible()
  expect(state.saves).toEqual([{ preflight_id: 'fixture-preflight', confirmation: '恢复备份', current_password: 'browser-fixture-password' }])
  await expect(page.getByText('等待执行', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '预检恢复', exact: true }).click()
  await page.getByRole('button', { name: '运行预检', exact: true }).click()
  await expect(dialog.getByRole('textbox', { name: '当前密码', exact: true })).toHaveValue('')
})

test('预检失败显示错误并允许重试', async ({ page }) => {
  const state = await setup(page); state.fail = true; await page.goto('/tasks/backups')
  await page.getByRole('button', { name: '预检恢复', exact: true }).click()
  await page.getByRole('button', { name: '运行预检', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '预检失败' })).toBeVisible()
  state.fail = false; await page.getByRole('button', { name: '运行预检', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '当前密码', exact: true })).toBeVisible()
  expect(state.saves).toHaveLength(0)
})

for (const mode of ['read', 'offline'] as const) test(`${mode} 禁止恢复`, async ({ page }, info) => {
  const state = await setup(page, mode); await page.goto('/tasks/backups')
  await expect(page.getByRole('button', { name: '预检恢复', exact: true })).toBeDisabled()
  expect(state.saves).toHaveLength(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath(`backups-${mode}.png`), fullPage: true, animations: 'disabled' })
})
