import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const schedule = () => ({ key: 'files', name: '清理软删除文件', task: 'tasks.cleanup_soft_deleted_files', enabled: true,
  module_enabled: true, missing: false, revision: 'v1', cron: { minute: '0', hour: '3', day_of_week: '*', day_of_month: '*', month_of_year: '*', timezone: 'Asia/Shanghai' },
  options: { dry_run: false, batch_size: 100 }, supported: true, overlap: 'skip', time_limit_seconds: 300,
  preview: { id: 'preview-1', result: { eligible_files: 5, retention_days: 30 }, completed_at: '' },
  last_run: { id: 'run1', status: 'success', result: { eligible_files: 5, dry_run: true }, error: '', name: '清理软删除文件' },
})
async function setup(page: Page, options: { admin?: boolean; readOnly?: boolean; failed?: boolean; noPreview?: boolean; disabled?: boolean } = {}) {
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-maintenance-fixture'))
  const row = schedule()
  if (options.noPreview) Object.assign(row, { preview: null })
  if (options.disabled) row.module_enabled = false
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'a1', username: 'admin', is_staff: options.admin !== false, is_superuser: !options.readOnly && options.admin !== false, permissions: options.readOnly ? ['schedule:read'] : ['*'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/tasks/schedules/')) return route.fulfill(options.failed ? { status: 503, json: envelope(null) } : { json: envelope([row]) })
    if (path.endsWith('/tasks/schedules/files/')) return route.fulfill({ json: envelope({ ...row, revision: 'v2', ...route.request().postDataJSON() }) })
    if (path.endsWith('/tasks/schedules/files/run/')) return route.fulfill({ status: 202, json: envelope({ id: 'manual1', status: 'pending' }) })
    return route.fulfill({ json: envelope({ count: 0 }) })
  })
}

test('维护页面展示注册计划、预览和结果，窄屏无溢出', async ({ page }, info) => {
  await setup(page)
  await page.goto('/tasks/schedules')
  await expect(page.getByRole('heading', { name: '定时维护' })).toBeVisible()
  await expect(page.getByText('符合清理条件：5 项；保留 30 天')).toBeVisible()
  await expect(page.getByRole('button', { name: '执行清理', exact: true })).toBeEnabled()
  await expect(page.locator('.schedule .el-tag')).not.toHaveClass(/enter-active|enter-from/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('maintenance-page.png'), fullPage: true })
})

test('计划编辑包含版本、Cron、时区及白名单参数，保存后关闭', async ({ page }) => {
  await setup(page)
  await page.goto('/tasks/schedules')
  await page.getByRole('button', { name: '编辑计划' }).click()
  await page.getByLabel('分钟', { exact: true }).fill('*/15')
  await page.getByLabel('时区（IANA 名称）').fill('UTC')
  const request = page.waitForRequest(req => req.method() === 'PATCH')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  const payload = (await request).postDataJSON()
  expect(payload.revision).toBe('v1')
  expect(payload.minute).toBe('*/15')
  expect(payload.timezone).toBe('UTC')
  expect(payload.options.batch_size).toBe(100)
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('版本冲突保留输入，明确重新载入或取消会提示未保存', async ({ page }) => {
  await setup(page)
  await page.route('**/tasks/schedules/files/', route => route.fulfill({ status: 409, json: envelope(null) }))
  await page.goto('/tasks/schedules')
  await page.getByRole('button', { name: '编辑计划' }).click()
  await page.getByLabel('分钟', { exact: true }).fill('*/20')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('内容已被其他人修改，已保留输入，请刷新后重试')).toBeVisible()
  await expect(page.getByLabel('分钟', { exact: true })).toHaveValue('*/20')
  await page.getByRole('button', { name: '重新载入计划' }).click()
  await expect(page.getByText('计划有未保存内容，确定放弃吗？')).toBeVisible()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByLabel('分钟', { exact: true })).toHaveValue('0')
})

test('预览和实际执行使用幂等键、有效预览及确认文字', async ({ page }) => {
  await setup(page)
  await page.goto('/tasks/schedules')
  let request = page.waitForRequest(req => req.method() === 'POST' && req.url().endsWith('/run/'))
  await page.getByRole('button', { name: '运行预览' }).click()
  const first = await request
  expect(first.postDataJSON().options.dry_run).toBe(true)
  expect(first.headers()['idempotency-key']).toBeTruthy()
  await expect(page.getByRole('button', { name: '执行清理', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '执行清理', exact: true }).click()
  await expect(page.getByRole('button', { name: '确认执行' })).toBeDisabled()
  await page.getByLabel('清理确认文本').fill('执行清理')
  request = page.waitForRequest(req => req.method() === 'POST' && req.url().endsWith('/run/'))
  await page.getByRole('button', { name: '确认执行' }).click()
  expect((await request).postDataJSON()).toMatchObject({ confirmation: '执行清理', preview_id: 'preview-1', options: { dry_run: false } })
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('请求期间禁用重复提交，网络错误重试复用原幂等键', async ({ page }) => {
  await setup(page)
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  const keys: string[] = []
  await page.route('**/tasks/schedules/files/run/', async route => {
    keys.push(route.request().headers()['idempotency-key']); await held
    return route.fulfill({ status: 503, json: envelope(null) })
  })
  await page.goto('/tasks/schedules')
  await page.getByRole('button', { name: '运行预览' }).click()
  await expect(page.getByRole('button', { name: '编辑计划' })).toBeDisabled()
  release()
  await expect(page.getByText('提交失败，请刷新计划或重新预览后重试')).toBeVisible()
  await page.getByRole('button', { name: '运行预览' }).click()
  await expect.poll(() => keys.length).toBe(2)
  expect(keys[0]).toBe(keys[1])
})

test('加载失败可恢复，缺少预览禁止实际执行', async ({ page }) => {
  await setup(page, { failed: true })
  await page.goto('/tasks/schedules')
  await expect(page.getByText('维护计划加载失败，请重试')).toBeVisible()
  await page.route('**/tasks/schedules/', route => route.fulfill({ json: envelope([{ ...schedule(), preview: null }]) }))
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('button', { name: '执行清理', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '运行预览' })).toBeEnabled()
})

test('只读权限隐藏操作，模块关闭禁用执行，非管理员转 403', async ({ page }) => {
  await setup(page, { readOnly: true })
  await page.goto('/tasks/schedules')
  await expect(page.getByRole('heading', { name: '定时维护' })).toBeVisible()
  await expect(page.getByRole('button', { name: '编辑计划' })).toHaveCount(0)
  await setup(page, { disabled: true })
  await page.reload()
  await expect(page.getByRole('button', { name: '运行预览' })).toBeDisabled()
  await setup(page, { admin: false })
  await page.reload()
  await expect(page).toHaveURL(/\/403$/)
})

test('英文深色模式编辑弹窗可用，无页面横向溢出', async ({ page }) => {
  await setup(page)
  await page.addInitScript(() => { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') })
  await page.goto('/tasks/schedules')
  await page.getByRole('button', { name: 'Edit schedule' }).click()
  await expect(page.getByLabel('Time zone (IANA name)')).toHaveValue('Asia/Shanghai')
  const bounds = await page.getByRole('dialog').boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
