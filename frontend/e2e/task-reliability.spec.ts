import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, allowed = true) {
  const state = { resumes: 0, cancels: 0, allowed }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-task-fixture'))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'owner', username: 'owner', permissions: state.allowed ? ['task:read', 'task:cancel', 'task:retry', 'data_io:import'] : ['task:read'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'tasks', title: 'Tasks', enabled: true, dependencies: [], paths: ['/tasks'] }] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/resume/')) { state.resumes++; return route.fulfill({ status: 202, json: envelope({}) }) }
    if (path.endsWith('/cancel/')) { state.cancels++; return route.fulfill({ json: envelope({}) }) }
    if (path.endsWith('/tasks/')) return route.fulfill({ json: envelope({ items: [{ id: 'resume1', request_id: 'task-origin-http-123', name: '保留已提交行的导入', creator: 'owner', task_type: 'import', status: 'failed', progress: 50, result: { created: 1 }, error: 'worker_lost_committed_rows_preserved', created_at: '2026-10-15T00:00:00Z',
      execution: { attempt: 1, can_resume: true, semantics: 'resume_uncommitted_rows', policy: { soft_timeout: 300, hard_timeout: 330, dispatch_attempts: 5 } } }], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } }) })
    return route.fulfill({ json: envelope({ count: 0 }) })
  })
  return state
}

test('接续需要明确确认，拒绝时不提交，结果展示策略和已提交统计', async ({ page }, info) => {
  const state = await setup(page)
  await page.goto('/tasks')
  await page.getByRole('button', { name: '接续未提交行', exact: true }).click()
  await expect(page.getByText('接续将跳过已提交的行和已记录的校验错误，仅执行剩余行；确定继续吗？')).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  expect(state.resumes).toBe(0)
  await page.getByRole('button', { name: '接续未提交行', exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect.poll(() => state.resumes).toBe(1)
  await page.getByRole('button', { name: '结果', exact: true }).click()
  await expect(page.getByText('300s / 330s')).toBeVisible()
  await expect(page.getByText('task-origin-http-123', { exact: true })).toBeVisible()
  await expect(page.locator('.result-json')).toContainText('"created": 1')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('task-reliability.png'), fullPage: true, animations: 'disabled' })
})

test('无接续权限仅能读取结果', async ({ page }) => {
  const state = await setup(page, false)
  await page.goto('/tasks')
  await expect(page.getByRole('cell', { name: '保留已提交行的导入', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '接续未提交行', exact: true })).toHaveCount(0)
  expect(state.resumes).toBe(0)
})

test('确认期间撤权后不发送接续请求', async ({ page }) => {
  await page.clock.install()
  const state = await setup(page)
  await page.goto('/tasks')
  await page.getByRole('button', { name: '接续未提交行', exact: true }).click()
  state.allowed = false
  await page.clock.fastForward(31000)
  await page.getByRole('button', { name: '确定', exact: true }).click()
  expect(state.resumes).toBe(0)
})
