import { expect, test, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, english = false) {
  await page.addInitScript(english => {
    localStorage.setItem('token', 'isolated-error-fixture')
    if (english) { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') }
  }, english)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'error-fixture', username: 'fixture', is_staff: true, permissions: ['*'] }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'system', paths: ['/system/cache'], dependencies: [], enabled: true }] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    return route.fulfill({ json: envelope({ count: 0, results: [], totals: {}, login_trend: [], task_status: {} }) })
  })
}

// Replace a requested compiled module only in this isolated browser test. No debug route or production hook.
const cacheChunk = /\/assets\/CacheManagementView-[^/]+\.js(?:\?.*)?$/
test('真实子树渲染错误显示可恢复边界，重试销毁旧页面且不泄露错误内容', async ({ page }, info) => {
  await setup(page)
  await page.route(cacheChunk, route => route.fulfill({ contentType: 'application/javascript', body:
    `let failed = true; export default { render() { if (failed) { failed = false; throw new Error('credential=private-error-marker') } return 'Recovered isolated page' } }` }))
  await page.goto('/system/cache')
  await expect(page.getByRole('heading', { name: '页面发生错误' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('当前未保存的输入将丢失')
  await expect(page.getByRole('heading', { name: '页面发生错误' })).toBeFocused()
  await expect(page.locator('body')).not.toContainText('private-error-marker')
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('private-error-marker'))).toBe(false)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('error-boundary.png'), fullPage: true })
  await page.getByRole('button', { name: '重新打开当前页面', exact: true }).click()
  await expect(page.getByText('Recovered isolated page', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('永久错误不自动刷新；返回首页走正常路由', async ({ page }) => {
  await setup(page)
  let loads = 0
  await page.route(cacheChunk, route => {
    loads++
    return route.fulfill({ contentType: 'application/javascript', body: `export default { render() { throw new Error('private-render') } }` })
  })
  await page.goto('/system/cache')
  await expect(page.getByRole('heading', { name: '页面发生错误' })).toBeVisible()
  await page.getByRole('button', { name: '重新打开当前页面', exact: true }).click()
  await expect(page.getByRole('heading', { name: '页面发生错误' })).toBeVisible()
  expect(loads).toBe(1)
  await page.getByRole('button', { name: '返回首页', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: '页面发生错误' })).toHaveCount(0)
})

test('路由懒加载失败进入错误页，无自动重载循环或原始错误泄露', async ({ page }) => {
  await setup(page)
  let loads = 0
  await page.route(cacheChunk, route => {
    loads++
    return route.fulfill({ contentType: 'application/javascript', body: `throw new Error('private-import-marker'); export default {}` })
  })
  await page.goto('/system/cache')
  await expect(page).toHaveURL(/\/500$/)
  await expect(page.getByRole('heading', { name: '服务暂时不可用' })).toBeVisible()
  await expect(page.locator('body')).not.toContainText('private-import-marker')
  expect(loads).toBe(1)
})

test('英文深色错误界面支持键盘恢复和窄屏布局', async ({ page }, info) => {
  await setup(page, true)
  await page.route(cacheChunk, route => route.fulfill({ contentType: 'application/javascript', body: `export default { render() { throw new Error('private') } }` }))
  await page.goto('/system/cache')
  await expect(page.getByRole('heading', { name: 'The page encountered an error' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Unsaved input on the current page will be lost')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Reopen current page', exact: true })).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('error-boundary-dark.png'), fullPage: true })
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Back to Dashboard', exact: true })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/$/)
})
