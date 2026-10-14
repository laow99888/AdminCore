import { test, expect, type Page } from '@playwright/test'

const env = (data: unknown) => ({ code: 200, message: 'success', data })
const paged = (items: unknown[]) => ({ items, pagination: { total: items.length, page: 1, page_size: 10, total_pages: 1 } })
async function setup(page: Page, realtime = true, unavailable = false) {
  const state = { streams: 0, reads: 0, permission: true, progress: 0 }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-realtime-fixture'))
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: env({ id: 'member', username: 'member', permissions: state.permission ? ['task:read'] : [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: env({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: env({ contract_version: 1, preset: 'standard', modules: ['tasks', 'notifications', 'approvals', 'realtime'].map(key => ({ key, title: key, enabled: key !== 'realtime' || realtime, dependencies: [], paths: key === 'realtime' ? [] : [`/${key}`] })) }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: env([]) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: env({ count: 1 }) })
    if (path.endsWith('/realtime/events/')) {
      state.streams++
      expect(request.url()).not.toContain('token=')
      expect(request.headers()['authorization']).toBe('Bearer isolated-realtime-fixture')
      if (unavailable) return route.fulfill({ status: 503, json: env(null) })
      state.progress = 41
      const topics = { notifications: { total: 3, unread_count: 3, changed_at: null, read_at: null }, approvals: { total: 1, todo_count: 1, changed_at: null },
        tasks: { total: 1, active_count: 1, changed_at: null, active: [{ id: '00000000-0000-4000-8000-000000000001', status: 'running', progress: 41 }] } }
      return route.fulfill({ contentType: 'text/event-stream; charset=utf-8', body: `: heartbeat\n\nevent: snapshot\ndata: ${JSON.stringify({ request_id: 'browser-fixture', topics })}\n\n` })
    }
    if (path.endsWith('/tasks/')) {
      state.reads++
      return route.fulfill({ json: env(paged([{ id: '00000000-0000-4000-8000-000000000001', name: '范围内任务', task_type: 'other', status: 'running', progress: state.progress, result: null, error: '', related_resource: '', created_at: '2026-10-15T00:00:00Z' }])) })
    }
    if (path.endsWith('/notifications/')) { state.reads++; return route.fulfill({ json: env(paged([{ id: 'n1', title: '范围内通知', content: '普通安全正文', is_read: false, notification_type: 'system', created_at: '2026-10-15T00:00:00Z' }])) }) }
    if (path.endsWith('/approvals/')) { state.reads++; return route.fulfill({ json: env(paged([])) }) }
    return route.fulfill({ json: env(paged([])) })
  })
  return state
}

test('快照更新通知徽标和任务进度，窄屏深色无溢出', async ({ page }, info) => {
  const state = await setup(page)
  await page.addInitScript(() => localStorage.setItem('theme', 'dark'))
  await page.goto('/tasks')
  await expect(page.getByRole('cell', { name: '范围内任务', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '41%', exact: true })).toBeVisible()
  await expect(page.locator('.el-badge__content').first()).toHaveText('3')
  await expect.poll(() => state.reads).toBeGreaterThan(1)
  expect(state.streams).toBeGreaterThan(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('realtime-tasks-dark.png'), fullPage: true })
})

test('服务不可用继续显示正常列表及轮询回退，不忙重连', async ({ page }) => {
  // install 本身仍随真实时间推进；并发回归的等待会吃掉一分钟边界。
  // 先在空文档暂停，再显式推进页面初始化与退避时间。
  await page.clock.install({ time: new Date('2026-10-15T00:00:00Z') })
  await page.clock.pauseAt(new Date('2026-10-15T00:01:00Z'))
  const state = await setup(page, true, true)
  await page.goto('/tasks')
  await page.clock.runFor(100)
  await expect(page.getByRole('cell', { name: '范围内任务', exact: true })).toBeVisible()
  await expect.poll(() => state.streams).toBe(1)
  await page.clock.fastForward(59000)
  expect(state.streams).toBe(1)
  await page.clock.fastForward(1500)
  await expect.poll(() => state.reads).toBeGreaterThan(1)
  await expect(page.getByRole('cell', { name: '范围内任务', exact: true })).toBeVisible()
})

test('模块默认关闭不建立流，通知保持现有读取', async ({ page }) => {
  const state = await setup(page, false)
  await page.goto('/notifications')
  await expect(page.getByText('范围内通知', { exact: true })).toBeVisible()
  await expect(page.locator('.el-badge__content').first()).toHaveText('1')
  expect(state.streams).toBe(0)
})

test('审批列表快照重取不清空未提交草稿', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/approvals')
  await page.getByRole('button', { name: '+ 发起申请', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '发起审批申请', exact: true })
  await dialog.getByLabel('标题', { exact: true }).fill('只存在内存的草稿')
  await expect.poll(() => state.reads).toBeGreaterThan(1)
  await expect(dialog.getByLabel('标题', { exact: true })).toHaveValue('只存在内存的草稿')
  expect(await page.evaluate(() => Object.values(localStorage).some(value => value.includes('只存在内存的草稿')))).toBe(false)
})
