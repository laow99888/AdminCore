import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, count = 100, english = false) {
  const calls: string[] = [], state = { count, denied: false, fail: false }
  await page.addInitScript(english => { localStorage.setItem('token', 'virtual-fixture'); localStorage.setItem('language', english ? 'en-US' : 'zh-CN'); localStorage.setItem('theme', 'dark') }, english)
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'virtual-member', username: 'member', permissions: state.denied ? [] : ['log:read'], is_staff: false }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.match(/\/logs\/(operation|login|exception)\/$/)) {
      calls.push(url.pathname + url.search)
      if (state.fail) return route.fulfill({ status: 503, json: { code: 503, message: 'synthetic unavailable', data: null } })
      const pageNumber = Number(url.searchParams.get('page') || 1)
      const items = Array.from({ length: state.count }, (_, index) => ({ id: `${pageNumber}-${index}`, created_at: '2026-10-15 08:00',
        description: `<script>virtual-${index}</script>`, username: `virtual-user-${pageNumber}-${index}`, level: 'ERROR', message: `virtual-message-${index}`, request_path: '/synthetic',
        action: 'read', resource: `virtual-row-${pageNumber}-${index}`, status: path.includes('/login/') ? 'success' : 200, ip_address: '192.0.2.1', error_message: '' }))
      return route.fulfill({ json: envelope({ items, pagination: { total: Math.max(state.count, 201), page: pageNumber, page_size: 100, total_pages: 3 } }) })
    }
    if (path.includes('/logs/operation/')) return route.fulfill({ json: { id: '1-0', description: 'synthetic-audit', audit_version: 1, before_values: {}, after_values: { version: 2 }, batch_results: [] } })
    return route.fulfill({ json: envelope({ count: 0, items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 0 } }) })
  })
  return { calls, state }
}
const toggle = (page: Page) => page.getByRole('checkbox', { name: /虚拟滚动（当前页）|Virtual scrolling \(current page\)/ })
const grid = (page: Page) => page.locator('.base-virtual-table')

test('日志可选虚拟视图，分页/详情/三类日志及恢复普通表格保留原请求契约', async ({ page }) => {
  const { calls } = await setup(page)
  await page.goto('/logs')
  await expect(page.locator('.base-table')).toBeVisible()
  await expect(toggle(page)).not.toBeChecked()
  const before = calls.length
  await toggle(page).check()
  await expect(grid(page)).toBeVisible()
  expect(calls.length).toBe(before)
  await expect(grid(page).getByText('virtual-row-1-0', { exact: true })).toBeVisible()
  await grid(page).getByRole('button', { name: '审计详情' }).first().click()
  await expect(page.getByRole('dialog')).toContainText('synthetic-audit')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await page.locator('.virtual-pagination .el-pager li').filter({ hasText: /^2$/ }).click()
  await expect(grid(page).getByText('virtual-row-2-0', { exact: true })).toBeVisible()
  expect(calls.some(value => value.includes('page=2') && value.includes('page_size=10'))).toBe(true)
  await page.getByRole('tab', { name: '登录日志', exact: true }).click()
  await expect(grid(page).getByText('virtual-user-1-0', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: '异常日志', exact: true }).click()
  await expect(grid(page).getByText('virtual-message-0', { exact: true })).toBeVisible()
  await toggle(page).uncheck()
  await expect(page.locator('.base-table')).toBeVisible()
  await expect(page.getByRole('cell', { name: 'virtual-message-0', exact: true })).toBeVisible()
})

test('一万行固定合成数据实际窗口化，滚动首尾与键盘操作，DOM行数有界', async ({ page }, info) => {
  // 刻意返回超出真实API分页的固定合成数据，仅验证渲染组件，不代表网络/后端容量。
  const { state } = await setup(page, 1)
  await page.goto('/logs')
  await toggle(page).check()
  state.count = 10000
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const viewport = grid(page).getByRole('region', { name: '系统日志' })
  await expect(grid(page).getByText('virtual-row-1-0', { exact: true })).toBeVisible()
  expect(await grid(page).locator('.el-table-v2__row').count()).toBeLessThan(30)
  await viewport.focus(); await page.keyboard.press('End')
  await expect(grid(page).getByText('virtual-row-1-9999', { exact: true })).toBeVisible()
  expect(await grid(page).locator('.el-table-v2__row').count()).toBeLessThan(30)
  await page.keyboard.press('Home')
  await expect(grid(page).getByText('virtual-row-1-0', { exact: true })).toBeVisible()
  await page.keyboard.press('PageDown')
  await expect.poll(async () => grid(page).locator('.el-table-v2__row').first().getAttribute('aria-rowindex')).not.toBe('2')
  await page.screenshot({ path: info.outputPath('virtual-10000.png'), fullPage: true })
})

test('空数据及不合格行数显示明确状态，仍可恢复普通表格', async ({ page }) => {
  const { state } = await setup(page, 0)
  await page.goto('/logs'); await toggle(page).check()
  await expect(grid(page).getByRole('status')).toContainText('暂无数据')
  state.count = 10001
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(grid(page).getByRole('alert')).toContainText('请使用普通表格')
  state.count = 1
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(grid(page).getByText('virtual-row-1-0', { exact: true })).toBeVisible()
  await toggle(page).uncheck(); await expect(page.locator('.base-table')).toBeVisible()
})

test('英文深色375px，键盘切换、横向滚动与触屏按钮无整页溢出', async ({ page }, info) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await setup(page, 100, true)
  await page.goto('/logs')
  await toggle(page).focus(); await page.keyboard.press('Space')
  await expect(grid(page)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await grid(page).getByRole('region', { name: 'System Logs' }).focus(); await page.keyboard.press('End')
  await expect(grid(page).getByText('virtual-row-1-99', { exact: true })).toBeVisible()
  const target = grid(page).getByRole('button', { name: 'Audit Details' }).last()
  await target.scrollIntoViewIfNeeded()
  expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  await page.screenshot({ path: info.outputPath('virtual-mobile-english.png'), fullPage: true })
})

test('离开页面不保留虚拟数据，重新进入默认普通表格，撤权移除旧视图', async ({ page }) => {
  const { state } = await setup(page)
  await page.goto('/logs'); await toggle(page).check(); await expect(grid(page)).toBeVisible()
  await page.goto('/'); await page.goto('/logs')
  await expect(toggle(page)).not.toBeChecked()
  await toggle(page).check(); state.denied = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page).toHaveURL(/\/403$/)
  await expect(grid(page)).toHaveCount(0)
})

test('加载失败保留筛选和页码，清除旧数据，重试后恢复当前页', async ({ page }) => {
  const { state } = await setup(page)
  await page.goto('/logs'); await toggle(page).check()
  await expect(grid(page).getByText('virtual-row-1-0', { exact: true })).toBeVisible()
  state.fail = true
  await page.locator('.virtual-pagination .el-pager li').filter({ hasText: /^2$/ }).click()
  await expect(page.getByRole('alert').filter({ hasText: '列表加载失败' })).toBeVisible()
  await expect(grid(page).getByText('virtual-row-1-0', { exact: true })).toHaveCount(0)
  state.fail = false
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(grid(page).getByText('virtual-row-2-0', { exact: true })).toBeVisible()
})
