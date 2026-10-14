import { expect, test, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const emptyPage = envelope({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 0 } })

async function setup(page: Page, options: { permissions?: string[]; enabled?: boolean; english?: boolean; fail?: boolean; hold?: boolean } = {}) {
  await page.addInitScript(english => {
    localStorage.setItem('token', 'isolated-export-fixture')
    localStorage.setItem('language', english ? 'en-US' : 'zh-CN')
    localStorage.setItem('theme', 'dark')
  }, options.english || false)
  const exports: URL[] = []
  let release = () => {}
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'export-member', username: 'export_member', permissions: options.permissions || ['*'] }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules:
      ['data_io', 'files', 'tasks'].map(key => ({ key, title: key, enabled: options.enabled !== false, dependencies: [], paths: key === 'files' ? ['/files'] : [] })) }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/data-io/export/')) {
      expect(route.request().headers().authorization).toBe('Bearer isolated-export-fixture')
      expect(url.searchParams.has('token')).toBe(false)
      exports.push(url)
      if (options.hold) await pending
      if (options.fail && exports.length === 1) return route.fulfill({ status: 413, json: { code: 413, message: '导出超过 5000 行，请缩小筛选范围；未生成部分文件', data: null } })
      return route.fulfill({ contentType: 'text/csv', body: '\uFEFFusername\nfixture\n', headers: { 'Content-Disposition': 'attachment; filename="fixture.csv"' } })
    }
    return route.fulfill({ json: emptyPage })
  })
  return { exports, release }
}

async function download(page: Page, name = '导出 CSV') {
  const event = page.waitForEvent('download')
  await page.getByRole('button', { name, exact: true }).click()
  return event
}

test('四个真实列表入口用认证 Blob 导出 CSV/XLSX，下载文件名与格式对应', async ({ page }) => {
  const state = await setup(page)
  for (const [path, resource] of [['/users', 'users'], ['/roles', 'roles'], ['/logs', 'logs'], ['/files', 'files']]) {
    await page.goto(path!)
    const csv = await download(page)
    expect(csv.suggestedFilename()).toBe(`${resource}-export.csv`)
    const xlsx = await download(page, '导出 XLSX')
    expect(xlsx.suggestedFilename()).toBe(`${resource}-export.xlsx`)
    expect(state.exports.at(-1)!.searchParams.get('resource')).toBe(resource)
    expect(state.exports.at(-1)!.searchParams.get('export_format')).toBe('xlsx')
    expect(state.exports.at(-1)!.searchParams.has('page')).toBe(false)
  }
})

test('用户导出只带已应用的搜索条件，不把未搜索的输入当筛选结果', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/users')
  const search = page.getByPlaceholder('搜索用户名 / 邮箱')
  await search.fill('applied-user')
  const loaded = page.waitForResponse(response => response.url().includes('/users/?') && response.url().includes('applied-user'))
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await loaded
  await search.fill('unsent-draft')
  await download(page)
  expect(state.exports.at(-1)!.searchParams.get('search')).toBe('applied-user')
})

test('日志导出使用当前类型及已应用搜索，不混合三种日志', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/logs')
  await page.getByRole('tab', { name: '登录日志', exact: true }).click()
  await page.getByPlaceholder('搜索描述 / 用户名').fill('operator')
  const loaded = page.waitForResponse(response => response.url().includes('/logs/login/?') && response.url().includes('operator'))
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await loaded
  await download(page)
  expect(state.exports.at(-1)!.searchParams.get('log_type')).toBe('login')
  expect(state.exports.at(-1)!.searchParams.get('search')).toBe('operator')
  await page.getByRole('tab', { name: '异常日志', exact: true }).click()
  await download(page)
  expect(state.exports.at(-1)!.searchParams.get('log_type')).toBe('exception')
})

test('缺导出权限或模块关闭时不展示入口，文件沿用下载权限', async ({ page }) => {
  await setup(page, { permissions: ['user:read', 'role:read', 'log:read', 'file:download'] })
  await page.goto('/users')
  await expect(page.getByRole('button', { name: '导出 CSV', exact: true })).toHaveCount(0)
  await page.unroute('**/api/v1/**')
  await setup(page, { enabled: false })
  await page.goto('/users')
  await expect(page.getByRole('button', { name: '导出 CSV', exact: true })).toHaveCount(0)
  await page.unroute('**/api/v1/**')
  await setup(page, { permissions: ['data_io:export', 'file:download'] })
  await page.goto('/files')
  await expect(page.getByRole('button', { name: '导出 CSV', exact: true })).toBeVisible()
})

test('请求期间阻止重复导出，超限显示明确错误并允许重试', async ({ page }) => {
  const state = await setup(page, { hold: true, fail: true })
  await page.goto('/roles')
  await page.getByRole('button', { name: '导出 CSV', exact: true }).click()
  await expect.poll(() => state.exports.length).toBe(1)
  await expect(page.getByRole('button', { name: '导出 XLSX', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '导出 CSV', exact: true }).evaluate(button => { button.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
  expect(state.exports).toHaveLength(1)
  state.release()
  await expect(page.locator('.export-error')).toHaveText('导出超过 5000 行，请缩小筛选范围；未生成部分文件')
  await download(page)
  expect(state.exports).toHaveLength(2)
  await expect(page.locator('.export-error')).toHaveCount(0)
})

test('英文暗色窄屏导出按钮可访问且控件不超出视口', async ({ page }) => {
  await setup(page, { english: true })
  await page.goto('/users')
  const controls = page.getByRole('group', { name: 'Export filtered results', exact: true })
  await expect(controls).toBeVisible()
  for (const name of ['Export CSV', 'Export XLSX']) {
    const button = controls.getByRole('button', { name, exact: true })
    const bounds = await button.boundingBox()
    expect(bounds!.height).toBeGreaterThanOrEqual(44)
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  }
  expect((await download(page, 'Export CSV')).suggestedFilename()).toBe('users-export.csv')
})
