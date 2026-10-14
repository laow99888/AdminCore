import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const row = { id: 'audit-1', created_at: '2026-10-15T00:00:00Z', action: 'update', resource: 'user', status: 200, description: 'safe change', audit_version: 1, actor_identifier: 'actor-fixture', request_id: 'request-fixture', task_record_id: 'task-fixture', before_values: { is_active: true }, after_values: { is_active: false, username: '<img src=x onerror=window.auditInjected=1>' }, batch_results: [{ id: 'item-fixture', status: 200 }] }
async function setup(page: Page) {
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-audit-fixture'))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: '审计验收' }) })
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'admin-fixture', username: 'admin', is_staff: true, permissions: ['*'] }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: ['files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization'].map(key => ({ key, enabled: false, paths: key === 'data_io' ? [] : [`/${key}`], dependencies: [] })) }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'm1', name: '系统日志', path: '/logs', children: [] }, { id: 'm2', name: '用户管理', path: '/users', children: [] }]) })
    if (path.endsWith('/logs/operation/audit-1/')) return route.fulfill({ json: row })
    if (path.endsWith('/logs/operation/')) return route.fulfill({ json: envelope({ items: [row], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } }) })
    return route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 1 } }) })
  })
  await page.goto('/logs')
  await expect(page.getByRole('button', { name: '审计详情', exact: true })).toBeVisible()
}

test('审计详情展示关联与前后值，安全文本且窄屏暗色可读', async ({ page }, testInfo) => {
  await setup(page)
  await page.getByRole('button', { name: '切换到深色模式', exact: true }).click()
  const trigger = page.getByRole('button', { name: '审计详情', exact: true })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: '审计详情' })
  await expect(dialog.getByText('actor-fixture', { exact: true })).toBeVisible()
  await expect(dialog.getByText('request-fixture', { exact: true })).toBeVisible()
  await expect(dialog.getByText('task-fixture', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('heading', { name: '变更前' })).toBeVisible()
  await expect(dialog.getByRole('heading', { name: '逐项结果' })).toBeVisible()
  await expect(dialog.locator('pre').nth(1)).toContainText('<img src=x onerror=window.auditInjected=1>')
  expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).auditInjected)).toBeUndefined()
  expect(await dialog.locator('img').count()).toBe(0)
  const bounds = await dialog.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.screenshot({ path: testInfo.outputPath('audit-dark.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
})

test('详情失败可重试，旧日志明确没有结构化前后值', async ({ page }) => {
  await setup(page)
  let attempts = 0
  await page.route('**/api/v1/logs/operation/audit-1/', route => route.fulfill(++attempts === 1
    ? { status: 503, json: { code: 503, message: 'fixture unavailable', data: null } }
    : { json: { ...row, audit_version: 0, before_values: null, after_values: null, batch_results: [], description: 'legacy fixture' } }))
  await page.getByRole('button', { name: '审计详情', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '审计详情' })
  await expect(dialog.getByRole('alert')).toContainText('审计详情加载失败，请重试')
  await dialog.getByRole('button', { name: '重试', exact: true }).click()
  await expect(dialog.getByText('此记录未登记结构化前后值，以下内容为原日志描述。')).toBeVisible()
  await expect(dialog.getByText('legacy fixture', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('heading', { name: '变更前' })).toHaveCount(0)
})

test('切换日志页签丢弃尚未完成的审计详情响应', async ({ page }) => {
  await setup(page)
  let release!: () => void
  const hold = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/logs/operation/audit-1/', async route => { await hold; await route.fulfill({ json: row }) })
  const request = page.waitForRequest('**/api/v1/logs/operation/audit-1/')
  await page.getByRole('button', { name: '审计详情', exact: true }).click()
  await request
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: '登录日志', exact: true }).click()
  release()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await page.getByRole('tab', { name: '操作日志', exact: true }).click()
  await expect(page.getByText('actor-fixture', { exact: true })).toHaveCount(0)
})

test('英文审计详情和关闭页面后不保留旧详情', async ({ page }) => {
  await setup(page)
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await page.getByRole('menuitem', { name: 'English', exact: true }).click()
  await page.getByRole('button', { name: 'Audit details', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Audit details' })
  await expect(dialog.getByText('Actor identifier', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'Before change', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.goto('/users')
  await page.goto('/logs')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page.getByText('actor-fixture', { exact: true })).toHaveCount(0)
})
