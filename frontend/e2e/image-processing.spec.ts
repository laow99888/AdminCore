import { test, expect, type Page } from '@playwright/test'
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3XcAAAAASUVORK5CYII=', 'base64')
async function setup(page: Page, { enabled = true, permission = true, failure = false, delayed = false } = {}) {
  await page.addInitScript(() => localStorage.setItem('token', 'image-fixture'))
  let calls = 0
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'member', username: 'member', permissions: permission ? ['file:process', 'file:download'] : ['file:download'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'files', title: 'Files', enabled: true, paths: ['/files'], dependencies: [] }] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/files/')) return route.fulfill({ json: envelope({ items: [{ id: 'f1', original_name: 'private.png', file_type: 'png', size: 500, lifecycle_version: 1 }], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } }) })
    if (path.endsWith('/processing_config/')) return route.fulfill({ json: envelope({ enabled }) })
    if (path.endsWith('/transform/')) {
      calls++
      expect(route.request().headers().authorization).toBe('Bearer image-fixture')
      expect(route.request().postData()).toContain('lifecycle_version')
      if (delayed) await new Promise(resolve => setTimeout(resolve, 1000))
      if (failure && calls === 1) return route.fulfill({ status: 409, json: { code: 409, message: '记录已变化，请刷新后重试', data: null } })
      return route.fulfill({ contentType: 'image/webp', body: png })
    }
    return route.fulfill({ json: envelope({ count: 0 }) })
  })
  await page.goto('/files')
  return () => calls
}

test('可选能力和专门权限共同控制入口', async ({ page }) => {
  await setup(page, { enabled: false })
  await expect(page.getByRole('button', { name: '图片处理', exact: true })).toHaveCount(0)
  await setup(page, { permission: false })
  await expect(page.getByRole('button', { name: '图片处理', exact: true })).toHaveCount(0)
})

test('变换失败保留输入可重试，修改参数释放结果，关闭草稿可取消', async ({ page }) => {
  const calls = await setup(page, { failure: true })
  await page.getByRole('button', { name: '图片处理', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '图片处理', exact: true })
  const width = dialog.getByRole('spinbutton', { name: '最大宽度（px）', exact: true })
  await width.fill('320')
  await dialog.getByRole('button', { name: '生成预览', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('记录已变化')
  await expect(width).toHaveValue('320')
  await dialog.getByRole('button', { name: '生成预览', exact: true }).click()
  await expect(dialog.getByRole('img', { name: '处理结果预览', exact: true })).toBeVisible()
  expect(calls()).toBe(2)
  await width.fill('400')
  await expect(dialog.getByRole('img', { name: '处理结果预览', exact: true })).toHaveCount(0)
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  const prompt = page.getByRole('dialog', { name: '提示', exact: true })
  await prompt.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog).toBeVisible(); await expect(width).toHaveValue('400')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await prompt.getByRole('button', { name: '确定', exact: true }).click()
  await expect(dialog).toBeHidden()
})

test('双击一次请求，取消处理中止迟到结果', async ({ page }) => {
  const calls = await setup(page, { delayed: true })
  await page.getByRole('button', { name: '图片处理', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '图片处理', exact: true })
  // 首次点击立即禁用按钮，浏览器不再向服务器发第二次。
  await dialog.getByRole('button', { name: '生成预览', exact: true }).click()
  await expect(dialog.getByRole('button', { name: '生成预览', exact: true })).toBeDisabled()
  await expect(dialog.getByRole('status')).toBeVisible()
  await dialog.getByRole('button', { name: '取消请求', exact: true }).click()
  await expect(dialog.getByRole('status')).toHaveCount(0)
  await page.waitForTimeout(1200)
  await expect(dialog.getByRole('img', { name: '处理结果预览', exact: true })).toHaveCount(0)
  expect(calls()).toBe(1)
})

test('英文暗色及窄屏表单可读，无页面溢出', async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') })
  await setup(page)
  await page.getByRole('button', { name: 'Image Processing', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Image Processing', exact: true })
  await expect(dialog.getByRole('spinbutton', { name: 'Maximum Width (px)' })).toBeVisible()
  const bounds = (await dialog.boundingBox())!
  expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('processing-dark-en.png'), fullPage: true })
})
