import { test, expect, type Page } from '@playwright/test'
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const paged = (items: unknown[]) => envelope({ items, pagination: { total: items.length, page: 1, page_size: 20, total_pages: 1 } })
const initial = (kind: string): Record<string, any> => kind === 'config' ? { key: 'brand.name', label: '产品名称', kind: 'string', value: 'original', default: 'original', version: 1, minimum: 1, maximum: 100, effective: '下次读取生效' }
  : kind === 'schedule' ? { key: 'files', name: '清理软删除文件', task: 'tasks.cleanup_soft_deleted_files', enabled: true, module_enabled: true, supported: true, missing: false, revision: 'opaque-revision-one', cron: { minute: '0', hour: '3', day_of_week: '*', day_of_month: '*', month_of_year: '*', timezone: 'UTC' }, options: { dry_run: true, batch_size: 20 }, time_limit_seconds: 300, requires_preview: true, confirmation: '执行清理', preview: null, last_run: null }
  : kind === 'announcement' ? { id: 'a1', title: 'original', content: 'body', content_format: 'plain', status: 'draft', version: 1, published_at: null, created_at: '2026-10-16T00:00:00Z', updated_at: '2026-10-16T00:00:00Z' }
  : { id: 't1', code: 'fixture', name: 'original', enabled: true, revision: 1, current: { id: 'v1', number: 1, subject: 'original subject', body: 'body', variables: [], created_at: '' } }
const cases = [
  { kind: 'config', route: '/system/config', list: '/system/config/', detail: '/system/config/brand.name/', label: '产品名称', field: 'value', version: 'version', value: 'local draft', latest: 'server latest', trigger: '' },
  { kind: 'schedule', route: '/tasks/schedules', list: '/tasks/schedules/', detail: '/tasks/schedules/files/', label: '分钟', field: 'minute', version: 'revision', value: '*/15', latest: '*/20', trigger: '编辑计划' },
  { kind: 'announcement', route: '/notifications/announcements', list: '/notifications/announcements/manage/', detail: '/notifications/announcements/manage/a1/', label: '标题', field: 'title', version: 'version', value: 'local draft', latest: 'server latest', trigger: '编辑' },
  { kind: 'template', route: '/notifications/templates', list: '/notifications/templates/', detail: '/notifications/templates/t1/', label: '模板名称', field: 'name', version: 'revision', value: 'local draft', latest: 'server latest', trigger: '编辑' },
]
async function setup(page: Page, item: typeof cases[number], published = false) {
  let row = initial(item.kind), attempted = false
  const writes: Record<string, any>[] = []
  await page.addInitScript(() => { localStorage.setItem('token', 'isolated-extended-conflict-fixture'); localStorage.setItem('locale', 'zh-CN') })
  await page.route('**/api/v1/**', route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    if (path === '/modules/') return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'notifications', enabled: true, paths: ['/notifications'], dependencies: [] }] }) })
    if (path === '/auth/me/') return route.fulfill({ json: envelope({ id: 'admin', username: 'admin', is_staff: true, is_superuser: true, permissions: ['*'] }) })
    if (path === '/brand/') return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: 'fixture' }) })
    if (path === '/permissions/menus/my_menu/') return route.fulfill({ json: envelope([]) })
    if (path === item.detail && request.method() === 'PATCH') {
      const body = request.postDataJSON(); writes.push(body)
      if (!attempted) {
        attempted = true
        row = { ...row, [item.version]: item.kind === 'schedule' ? 'opaque-revision-two' : 2 }
        if (item.kind === 'schedule') row.cron = { ...row.cron, minute: item.latest }
        else row[item.field] = item.latest
        if (published) row.status = 'published'
      }
      if (body[item.version] !== row[item.version]) return route.fulfill({ status: 409, json: { code: 409, message: 'conflict', data: null } })
      if (item.kind === 'config') row.value = body.value
      else if (item.kind === 'schedule') row.cron.minute = body.minute
      else Object.assign(row, body)
      return route.fulfill({ json: envelope(item.kind === 'config' ? [row] : row) })
    }
    if (path === item.detail && request.method() === 'GET') return route.fulfill({ json: envelope(item.kind === 'config' ? [row] : row) })
    if (path === item.list) return route.fulfill({ json: item.kind === 'config' || item.kind === 'schedule' ? envelope([row]) : paged([row]) })
    if (path === '/notifications/announcements/') return route.fulfill({ json: paged([]) })
    return route.fulfill({ json: envelope({ count: 0 }) })
  })
  return { writes }
}
async function open(page: Page, item: typeof cases[number]) {
  await page.goto(item.route)
  if (item.kind === 'announcement') await page.locator('.el-radio-button').filter({ hasText: '公告管理' }).click()
  if (item.trigger) await page.getByRole('button', { name: item.trigger, exact: true }).first().click()
  return item.kind === 'config' ? page.locator('.config-form') : page.getByRole('dialog')
}
for (const item of cases) test(`${item.kind} 同窗比较、显式替换、使用最新版本提交`, async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message))
  const { writes } = await setup(page, item), editor = await open(page, item)
  const input = editor.getByLabel(item.label, { exact: true })
  await input.fill(item.value)
  const save = editor.getByRole('button', { name: item.kind === 'schedule' || item.kind === 'config' ? '保存' : '确认', exact: true })
  await save.click()
  const panel = page.getByRole('region', { name: '编辑冲突' })
  await expect(panel).toBeVisible(); await expect(input).toHaveValue(item.value); await expect(save).toBeDisabled()
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.getByRole('table')).toContainText(item.latest); await expect(input).toHaveValue(item.value)
  expect(writes).toHaveLength(1)
  await panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click()
  await expect(input).toHaveValue(item.latest)
  const reviewed = item.kind === 'schedule' ? '*/25' : 'reviewed final'
  await input.fill(reviewed); await save.click()
  await expect.poll(() => writes.length).toBe(2)
  expect(writes[0]![item.version]).toBe(item.kind === 'schedule' ? 'opaque-revision-one' : 1)
  expect(writes[1]![item.version]).toBe(item.kind === 'schedule' ? 'opaque-revision-two' : 2)
  expect(writes[1]![item.field]).toBe(reviewed)
  await expect(panel).not.toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(errors).toEqual([])
})

test('公告最新状态已发布时可比较和载入，但必须撤回后才能编辑', async ({ page }) => {
  const item = cases[2]!, { writes } = await setup(page, item, true), editor = await open(page, item)
  await editor.getByLabel('标题', { exact: true }).fill('draft')
  await editor.getByRole('button', { name: '确认', exact: true }).click()
  const panel = editor.getByRole('region', { name: '编辑冲突' })
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.getByRole('table')).toContainText('已发布')
  await panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click()
  await expect(editor.getByLabel('标题', { exact: true })).toBeDisabled()
  await expect(editor.getByRole('button', { name: '确认', exact: true })).toBeDisabled()
  await editor.locator('form').dispatchEvent('submit'); expect(writes).toHaveLength(1)
})
