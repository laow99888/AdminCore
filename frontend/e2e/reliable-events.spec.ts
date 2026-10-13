import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const event = { id: 'e1', topic: 'notification.created', status: 'failed', attempts: 2, available_at: '2026-10-13T20:00:00+08:00', last_error: 'recipient_missing', request_id: 'request-identifier'.repeat(8), published_at: null, created_at: '', updated_at: '' }
async function setup(page: Page, admin = true, failList = false) {
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-events-fixture'))
  let retried = false
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'a1', username: 'admin', is_staff: admin, is_superuser: admin, permissions: ['*'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/retry/')) { retried = true; return route.fulfill({ json: envelope({ ...event, status: 'pending' }) }) }
    if (path.endsWith('/events/e1/')) return route.fulfill({ json: envelope(event) })
    if (path.endsWith('/events/')) return route.fulfill(failList ? { status: 503, json: envelope(null) } : { json: envelope({ items: [{ ...event, status: retried ? 'pending' : event.status }], pagination: { total: 1, total_pages: 1, page: 1, page_size: 10 } }) })
    return route.fulfill({ json: envelope({ count: 0 }) })
  })
}

test('管理员查看详情并重试失败事件，桌面和窄屏弹窗可见', async ({ page }) => {
  await setup(page)
  await page.goto('/reliability/events')
  await page.getByRole('button', { name: '详情', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('recipient_missing')).toBeVisible()
  const bounds = await dialog.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '重新派发', exact: true }).click()
  const request = page.waitForRequest(req => req.method() === 'POST' && req.url().endsWith('/events/e1/retry/'))
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await request
  await expect(page.getByText('已提交重试', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '重新派发', exact: true })).toHaveCount(0)
})

test('列表失败提供刷新恢复入口，不显示陈旧记录', async ({ page }) => {
  await setup(page, true, true)
  await page.goto('/reliability/events')
  await expect(page.getByText('事件记录加载失败，请重试')).toBeVisible()
  await expect(page.getByRole('button', { name: '详情', exact: true })).toHaveCount(0)
  await page.route('**/api/v1/reliability/events/**', route => route.fulfill({ json: envelope({ items: [], pagination: { total: 0, total_pages: 1, page: 1, page_size: 10 } }) }))
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByText('事件记录加载失败，请重试')).toHaveCount(0)
  await expect(page.getByText('暂无数据')).toBeVisible()
})

test('普通用户即使有通配权限仍不能访问管理员事件页', async ({ page }) => {
  await setup(page, false)
  let requested = false
  page.on('request', req => { if (req.url().includes('/reliability/events/')) requested = true })
  await page.goto('/reliability/events')
  await expect(page).toHaveURL(/\/403$/)
  expect(requested).toBe(false)
})

test('重试冲突保留失败记录，按钮可以再次使用', async ({ page }) => {
  await setup(page)
  await page.route('**/api/v1/reliability/events/e1/retry/', route => route.fulfill({ status: 409, json: { code: 409, message: '只能重试失败事件', data: null } }))
  await page.goto('/reliability/events')
  await page.getByRole('button', { name: '重新派发', exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText('重试提交失败，请刷新状态后重试')).toBeVisible()
  await expect(page.getByRole('button', { name: '重新派发', exact: true })).toBeEnabled()
})
