import { test, expect, type Page, type TestInfo } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { read, utils, type WorkBook } from 'xlsx'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const unsafe = '=HYPERLINK("https://evil.test","中文")'
const button = (page: Page) => page.getByRole('button', { name: /^(本地 Excel（当前页）|Local Excel \(current page\))$/ })

async function setup(page: Page, options: { empty?: boolean; failSecond?: boolean; english?: boolean; disabled?: boolean; noExportPermission?: boolean; hold?: boolean } = {}) {
  const access = { permissions: options.noExportPermission ? ['user:read', 'role:read', 'log:read', 'file:download'] : ['*'] }
  let failed = false, release = () => {}
  const pending = new Promise<void>(resolve => { release = resolve })
  const calls: string[] = []
  await page.addInitScript(english => {
    localStorage.setItem('token', 'local-workbook-fixture')
    localStorage.setItem('language', english ? 'en-US' : 'zh-CN')
    localStorage.setItem('theme', 'dark')
  }, options.english || false)
  await page.route(/\/(?:logs|users|roles|files)(?:\?.*)?$/, async route => {
    if (!route.request().isNavigationRequest()) return route.continue()
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': "default-src 'self'; script-src 'self'; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'" } })
  })
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    calls.push(url.pathname + url.search)
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'export-member', username: 'member', permissions: access.permissions, is_staff: true }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: ['data_io', 'files'].map(key => ({ key, title: key, enabled: !(key === 'data_io' && options.disabled), dependencies: [], paths: key === 'files' ? ['/files'] : [] })) }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/files/processing_config/')) return route.fulfill({ json: envelope({ enabled: false }) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (/\/(users|roles|files)\/$/.test(path) || path.includes('/logs/')) {
      if (options.hold) await pending
      const current = Number(url.searchParams.get('page') || 1)
      if (options.failSecond && current === 2 && !failed) {
        failed = true
        return route.fulfill({ status: 503, json: { code: 503, message: 'isolated list failure', data: null } })
      }
      const row = { id: 'row-' + current, username: 'member-page-' + current, name: unsafe, description: unsafe,
        email: 'v***@example.test', phone: '138****3210', first_name: unsafe, last_name: '中文😀\n第二行', is_active: true, is_staff: true, roles: [], login_count: 0,
        original_name: unsafe, file_type: 'png', size: 32, size_display: '32 B', uploader_name: 'member', created_at: '2026-10-15 12:00:00',
        action: 'read', resource: unsafe, status: path.includes('/login/') ? 'success' : 200, level: 'ERROR',
        password: 'private-password-never-export', storage_path: 'private-storage-path-never-export', request_data: { token: 'private-token-never-export' }, message: 'private-stack-never-export' }
      return route.fulfill({ json: envelope({ items: options.empty ? [] : [row], pagination: { total: options.empty ? 0 : 21, page: current, page_size: 10, total_pages: 3 } }) })
    }
    return route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 0 } }) })
  })
  return { calls, release, revoke: () => { access.permissions = ['user:read', 'role:read', 'log:read', 'file:download'] } }
}
async function download(page: Page, info: TestInfo, filename: string): Promise<WorkBook> {
  const event = page.waitForEvent('download')
  await button(page).click()
  const result = await event
  expect(result.suggestedFilename()).toBe(filename)
  const path = info.outputPath(filename)
  await result.saveAs(path)
  const workbook = read(await readFile(path), { type: 'buffer' })
  expect(workbook.SheetNames).toEqual(['Data', 'Export info'])
  for (const sheet of Object.values(workbook.Sheets)) for (const [key, cell] of Object.entries(sheet)) {
    if (!key.startsWith('!')) { expect(cell.t).toBe('s'); expect(cell.f).toBeUndefined(); expect(cell.l).toBeUndefined() }
  }
  expect(JSON.stringify(workbook)).not.toMatch(/private-(?:password|storage-path|token|stack)-never-export/)
  return workbook
}

test('四类列表真实 Worker 生成 XLSX、字段白名单和公式文本安全，无导出或额外列表请求', async ({ page }, info) => {
  const state = await setup(page)
  const workerRequests: string[] = []
  page.on('request', request => { if (request.url().includes('localWorkbook.worker')) workerRequests.push(request.url()) })
  await page.goto('/login')
  expect(workerRequests).toHaveLength(0)
  for (const [path, resource, columns] of [['/users', 'users', 6], ['/roles', 'roles', 3], ['/files', 'files', 4], ['/logs', 'logs', 4]] as const) {
    await page.goto(path)
    await expect(button(page)).toBeEnabled()
    const lists = state.calls.filter(call => /\/(users|roles|files|logs\/operation)\/?\?/.test(call)).length
    const workbook = await download(page, info, `${resource}-page-1.xlsx`)
    const rows = utils.sheet_to_json<string[]>(workbook.Sheets.Data!, { header: 1 })
    expect(rows).toHaveLength(2); expect(rows[0]).toHaveLength(columns)
    expect(rows[1]).toContain(unsafe)
    if (resource === 'users') { expect(rows[1]).toContain('v***@example.test'); expect(rows[1]).toContain('138****3210') }
    expect(utils.sheet_to_json(workbook.Sheets['Export info']!, { header: 1 })).toContainEqual(['当前页', '1'])
    expect(state.calls.filter(call => /\/(users|roles|files|logs\/operation)\/?\?/.test(call)).length).toBe(lists)
    expect(state.calls.some(call => call.includes('/data-io/export/'))).toBe(false)
    await expect(button(page)).toBeEnabled()
  }
  expect(workerRequests).toHaveLength(4)
})

test('换页仅下载新页；加载失败禁止把旧数据标为新页，恢复后可重试', async ({ page }, info) => {
  await setup(page, { failSecond: true })
  await page.goto('/users'); await expect(button(page)).toBeEnabled()
  const failed = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/users/') && new URL(response.url()).searchParams.get('page') === '2' && response.status() === 503)
  await page.locator('.el-pager .number').filter({ hasText: /^2$/ }).click(); await failed
  await expect(button(page)).toBeDisabled()
  await page.getByRole('button', { name: '重置', exact: true }).click(); await expect(button(page)).toBeEnabled()
  await page.locator('.el-pager .number').filter({ hasText: /^2$/ }).click(); await expect(button(page)).toBeEnabled()
  const workbook = await download(page, info, 'users-page-2.xlsx')
  expect(JSON.stringify(workbook)).toContain('member-page-2')
  expect(JSON.stringify(workbook)).not.toContain('member-page-1')
  expect(utils.sheet_to_json(workbook.Sheets['Export info']!, { header: 1 })).toContainEqual(['当前页', '2'])
})

test('日志类型切换使用各自白名单，不把异常正文或请求原文导出', async ({ page }, info) => {
  await setup(page)
  await page.goto('/logs')
  for (const [name, columns] of [['登录日志', 3], ['异常日志', 2]] as const) {
    await page.getByRole('tab', { name, exact: true }).click(); await expect(button(page)).toBeEnabled()
    const workbook = await download(page, info, 'logs-page-1.xlsx')
    expect(utils.sheet_to_json<string[]>(workbook.Sheets.Data!, { header: 1 })[0]).toHaveLength(columns)
  }
})

test('空页和加载禁用，缺导出权限或模块关闭无入口', async ({ page }) => {
  for (const options of [{ empty: true }, { noExportPermission: true }, { disabled: true }, { hold: true }]) {
    await page.unrouteAll({ behavior: 'ignoreErrors' })
    const state = await setup(page, options)
    await page.goto('/users')
    if ('noExportPermission' in options || 'disabled' in options) await expect(button(page)).toHaveCount(0)
    else await expect(button(page)).toBeDisabled()
    state.release()
  }
})

test('Worker载入失败明确报错、解除锁，重试成功下载', async ({ page }, info) => {
  await setup(page)
  let first = true
  await page.route('**/assets/localWorkbook.worker-*.js', route => {
    if (first) { first = false; return route.abort('failed') }
    return route.continue()
  })
  await page.goto('/users'); await expect(button(page)).toBeEnabled(); await button(page).click()
  await expect(page.getByRole('alert')).toContainText('本地导出失败')
  await expect(button(page)).toBeEnabled()
  await download(page, info, 'users-page-1.xlsx')
  await expect(page.locator('.local-export-error')).toHaveCount(0)
})

test('Worker处理期间取消或失权后不下载晚到结果', async ({ page }) => {
  const state = await setup(page)
  const downloads: string[] = []
  page.on('download', result => { downloads.push(result.suggestedFilename()) })
  let release = () => {}, gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/assets/localWorkbook.worker-*.js', async route => { await gate; await route.continue().catch(() => {}) })
  await page.goto('/users'); await expect(button(page)).toBeEnabled(); await button(page).click()
  await expect(button(page)).toBeDisabled()
  await page.getByRole('button', { name: '取消本地导出', exact: true }).click()
  await expect(button(page)).toBeEnabled()
  release()
  await page.unroute('**/assets/localWorkbook.worker-*.js')
  gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/assets/localWorkbook.worker-*.js', async route => { await gate; await route.continue().catch(() => {}) })
  await button(page).click(); await expect(button(page)).toBeDisabled()
  state.revoke()
  const refreshed = page.waitForResponse(response => response.url().includes('/auth/me/'))
  await page.evaluate(() => window.dispatchEvent(new Event('focus'))); await refreshed
  await expect(button(page)).toHaveCount(0)
  release()
  expect(downloads).toHaveLength(0)
})

test('375px深色英文入口、键盘下载和页面不溢出', async ({ page }, info) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await setup(page, { english: true }); await page.goto('/users'); await expect(button(page)).toBeEnabled()
  expect(await button(page).evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await button(page).focus()
  const event = page.waitForEvent('download')
  await page.keyboard.press('Enter')
  const result = await event
  expect(result.suggestedFilename()).toBe('users-page-1.xlsx')
  await result.saveAs(info.outputPath('users-english.xlsx'))
  await page.screenshot({ path: info.outputPath('local-export-english.png'), fullPage: true })
})
