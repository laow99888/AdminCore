import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, english = false) {
  const state = { member: false, enabled: true, permissions: ['*'], failCatalog: false, failPreview: false,
    failClear: false, backend: 'shared', empty: false, overflow: false, expires: 120,
    previews: 0, catalogs: 0, clears: [] as unknown[], hold: undefined as Promise<void> | undefined }
  await page.addInitScript(english => {
    localStorage.setItem('token', 'isolated-cache-fixture')
    if (english) { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') }
  }, english)
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'cache-admin', username: 'admin', is_staff: !state.member, permissions: state.permissions }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'system', paths: ['/system/cache'], dependencies: [], enabled: state.enabled }] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/system/cache/')) {
      state.catalogs++
      return route.fulfill({ status: state.failCatalog ? 503 : 200, json: envelope({ backend: state.backend, limit: 1000, ttl_seconds: 300,
        namespaces: state.empty ? [] : ['configuration', 'dictionaries'].map(namespace => ({ namespace, module: 'system', candidate_count: state.overflow ? 1000 : namespace === 'configuration' ? 3 : 0, over_limit: state.overflow })) }) })
    }
    if (path.endsWith('/system/cache/preview/')) {
      state.previews++
      return route.fulfill({ status: state.failPreview ? 503 : 200, json: envelope({ namespace: route.request().postDataJSON().namespace,
        candidate_count: 3, backend: state.backend, expires_in: state.expires, token: `isolated-preview-${state.previews}` }) })
    }
    if (path.endsWith('/system/cache/clear/')) {
      state.clears.push(route.request().postDataJSON())
      if (state.hold) await state.hold
      return route.fulfill({ status: state.failClear ? 409 : 200, json: envelope({ outcome: 'completed' }) })
    }
    return route.fulfill({ json: envelope({ count: 0, totals: {}, login_trend: [], task_status: {} }) })
  })
  return state
}
const previewButton = (page: Page) => page.getByRole('button', { name: '预览清理 系统参数缓存', exact: true })

test('预览和确认分离，取消不清理；确认只发登记范围与令牌', async ({ page }, info) => {
  const state = await setup(page)
  await page.goto('/system/cache')
  await expect(page.getByRole('heading', { name: '缓存管理' })).toBeVisible()
  await previewButton(page).click()
  await expect(page.getByRole('dialog')).toContainText('候选数量: 3')
  expect(state.clears).toHaveLength(0)
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(state.clears).toHaveLength(0)
  await previewButton(page).click()
  await page.getByRole('button', { name: '确认清理', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '限定范围的清理已完成' })).toBeVisible()
  await expect(page.locator('.el-overlay:visible')).toHaveCount(0)
  expect(state.clears).toEqual([{ namespace: 'configuration', token: 'isolated-preview-2' }])
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes('isolated-preview-'))).toBe(false)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('cache-management.png'), fullPage: true })
})

test('只读目录和命名空间写权限控制清理入口', async ({ page }) => {
  const state = await setup(page)
  state.permissions = ['cache:read']
  await page.goto('/system/cache')
  await expect(page.getByText('系统参数缓存', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /预览清理/ })).toHaveCount(0)
  state.permissions = ['cache:read', 'cache:clear', 'dictionary:update']
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.getByRole('button', { name: '预览清理 字典选项缓存', exact: true })).toBeVisible()
  await expect(previewButton(page)).toHaveCount(0)
  expect(state.previews).toBe(0)
})

test('加载失败移除旧目录，刷新可恢复；预览失败不打开确认', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/system/cache')
  await expect(previewButton(page)).toBeVisible()
  state.failCatalog = true
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '缓存目录加载失败' })).toBeVisible()
  await expect(previewButton(page)).toHaveCount(0)
  state.failCatalog = false
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  state.failPreview = true
  await previewButton(page).click()
  await expect(page.getByRole('alert').filter({ hasText: '无法预览清理' })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(state.clears).toHaveLength(0)
})

test('版本冲突或失败丢弃确认，重新预览后才能重试', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/system/cache')
  await previewButton(page).click()
  state.failClear = true
  await page.getByRole('button', { name: '确认清理', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '清理未确认' })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  state.failClear = false
  await previewButton(page).click()
  await page.getByRole('button', { name: '确认清理', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '限定范围的清理已完成' })).toBeVisible()
  expect(state.clears).toEqual([{ namespace: 'configuration', token: 'isolated-preview-1' }, { namespace: 'configuration', token: 'isolated-preview-2' }])
})

test('执行中禁止取消、关闭和重复提交', async ({ page }) => {
  const state = await setup(page)
  let release!: () => void
  state.hold = new Promise<void>(resolve => { release = resolve })
  await page.goto('/system/cache')
  await previewButton(page).click()
  const confirm = page.getByRole('button', { name: '确认清理', exact: true })
  await confirm.click()
  await expect(confirm).toBeDisabled()
  await expect(page.getByRole('button', { name: '取消', exact: true })).toBeDisabled()
  await confirm.evaluate((button: HTMLButtonElement) => button.click())
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeVisible()
  expect(state.clears).toHaveLength(1)
  release()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('确认到期禁用，不自动重新发送旧预览', async ({ page }) => {
  await page.clock.install()
  const state = await setup(page)
  state.expires = 1
  await page.goto('/system/cache')
  await previewButton(page).click()
  await page.clock.fastForward(2000)
  await expect(page.getByRole('dialog')).toContainText('预览已过期')
  await expect(page.getByRole('button', { name: '确认清理', exact: true })).toBeDisabled()
  expect(state.clears).toHaveLength(0)
})

test('空目录、超限和不支持缓存有明确状态，进程内范围可见', async ({ page }) => {
  const state = await setup(page)
  state.backend = 'in_process'
  state.overflow = true
  await page.goto('/system/cache')
  await expect(page.getByText('进程内缓存：仅影响本次请求所在进程，其他进程不会同步清理。', { exact: true })).toBeVisible()
  await expect(previewButton(page)).toBeDisabled()
  state.overflow = false; state.backend = 'unsupported'
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(previewButton(page)).toBeDisabled()
  state.empty = true
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByText('暂无登记的缓存', { exact: true })).toBeVisible()
  expect(state.previews).toBe(0)
})

test('普通成员和关闭模块不能直接进入；已打开页面撤权后清除', async ({ page }) => {
  const state = await setup(page)
  state.member = true
  await page.goto('/system/cache')
  await expect(page).toHaveURL(/\/403$/)
  expect(state.catalogs).toBe(0)
  state.member = false; state.enabled = false
  await page.goto('/system/cache')
  await expect(page).toHaveURL(/\/$/)
  expect(state.catalogs).toBe(0)
  state.enabled = true
  await page.goto('/system/cache')
  await previewButton(page).click()
  state.permissions = []
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page).toHaveURL(/\/403$/)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(state.clears).toHaveLength(0)
})

test('英文深色、键盘预览及手机确认布局', async ({ page }, info) => {
  await setup(page, true)
  await page.goto('/system/cache')
  await expect(page.getByRole('heading', { name: 'Cache Management' })).toBeVisible()
  await page.getByRole('button', { name: 'Preview Cleanup: System Parameter Cache', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog')).toContainText('Candidate count: 3')
  await expect(page.locator('.el-overlay:visible')).not.toHaveClass(/enter-active|enter-from/)
  await expect(page.locator('html')).toHaveClass(/dark/)
  const dialog = await page.getByRole('dialog').boundingBox()
  expect(dialog!.x).toBeGreaterThanOrEqual(0)
  expect(dialog!.x + dialog!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('cache-confirmation-dark.png'), fullPage: true })
})
