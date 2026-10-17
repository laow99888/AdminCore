import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const csp = readFileSync('spa-csp.conf', 'utf8').match(/Content-Security-Policy "([^"]+)"/)![1]

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3XcAAAAASUVORK5CYII=', 'base64')

/** 真正的两页 PDF，第二页颜色不同；由浏览器实际运行 PDF.js worker。 */
function pdfFixture() {
  const streams = ['0 0 1 rg 0 0 200 300 re f 1 1 1 rg BT /F1 14 Tf 20 200 Td (Private PDF) Tj ET', '1 0 0 rg 0 0 200 300 re f']
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${streams[0].length} >>\nstream\n${streams[0]}\nendstream`,
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Resources << >> /Contents 6 0 R >>',
    `<< /Length ${streams[1].length} >>\nstream\n${streams[1]}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
  ]
  let text = '%PDF-1.4\n'
  const offsets = [0]
  for (let index = 0; index < objects.length; index++) {
    offsets.push(Buffer.byteLength(text))
    text += `${index + 1} 0 obj\n${objects[index]}\nendobj\n`
  }
  const start = Buffer.byteLength(text)
  text += `xref\n0 8\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n${start}\n%%EOF\n`
  return Buffer.from(text)
}

async function setup(page: Page, type = 'png', failure = false, delayed = false, access = 'isolated-preview-fixture') {
  // 在生产 CSP 下运行真实 PDF worker，不能依赖预览服务器较宽松的默认头。
  await page.route('**/files', async route => {
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': csp } })
  })
  await page.addInitScript(access => localStorage.setItem('token', access), access)
  const record = { id: 'f1', original_name: `private.${type}`, file_type: type, size: 500, size_display: '500 B', download_count: 0, created_at: '' }
  let previewRequests = 0
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'member', username: 'member', is_staff: false, is_superuser: false, permissions: ['*'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/files/')) return route.fulfill({ json: envelope({ items: [record], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } }) })
    if (path.endsWith('/preview/')) {
      previewRequests++
      expect(route.request().headers().authorization).toBe(`Bearer ${access}`)
      expect(route.request().url()).not.toContain('token=')
      if (delayed) await new Promise(resolve => setTimeout(resolve, 800))
      if (failure && previewRequests === 1) return route.fulfill({ status: 422, json: { code: 422, message: '文件内容损坏或与扩展名不符，无法预览', data: null } })
      return route.fulfill({ contentType: type === 'pdf' ? 'application/pdf' : 'image/png', body: type === 'pdf' ? pdfFixture() : png })
    }
    return route.fulfill({ json: envelope({ count: 0 }) })
  })
  await page.goto('/files')
  return () => previewRequests
}

test('图片通过认证 Blob 预览，关闭即释放 URL，窄屏无溢出', async ({ page }) => {
  await page.addInitScript(() => {
    const original = URL.revokeObjectURL.bind(URL)
    ;(window as any).revoked = []
    URL.revokeObjectURL = url => { (window as any).revoked.push(url); original(url) }
  })
  await setup(page)
  await page.getByRole('button', { name: '预览', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('img', { name: 'private.png' })).toBeVisible()
  await expect(dialog.getByRole('status')).toHaveCount(0)
  const url = await dialog.getByRole('img', { name: 'private.png' }).getAttribute('src')
  expect(url).toMatch(/^blob:/)
  const bounds = await dialog.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('image-preview.png'), fullPage: true })
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(await page.evaluate(() => (window as any).revoked)).toContain(url)
})

test('PDF 使用真实 worker 绘制并翻页，只在打开 PDF 时加载渲染器', async ({ page }) => {
  const resources: string[] = [], errors: string[] = []
  page.on('request', request => resources.push(request.url()))
  page.on('pageerror', error => errors.push(error.message))
  await setup(page, 'pdf')
  expect(resources.filter(url => /pdf-preview~pdf-|pdf.worker/.test(url))).toEqual([])
  await page.getByRole('button', { name: '预览', exact: true }).click()
  const dialog = page.getByRole('dialog'), canvas = dialog.locator('canvas')
  await expect(dialog.getByText('第 1 / 2 页')).toBeVisible()
  await expect(dialog.getByRole('button', { name: '下一页' })).toBeEnabled()
  const pixel = () => canvas.evaluate((element: HTMLCanvasElement) => [...element.getContext('2d')!.getImageData(5, 5, 1, 1).data])
  expect(await pixel()).toEqual([0, 0, 255, 255])
  const glyphPixels = await canvas.evaluate((element: HTMLCanvasElement) => {
    const { data } = element.getContext('2d')!.getImageData(0, 0, element.width, element.height)
    let white = 0
    for (let index = 0; index < data.length; index += 4) if (data[index]! > 200 && data[index + 1]! > 200 && data[index + 2]! > 200) white++
    return white
  })
  expect(glyphPixels).toBeGreaterThan(30)
  await expect(dialog.getByRole('button', { name: '上一页' })).toBeDisabled()
  await dialog.getByRole('button', { name: '下一页' }).click()
  await expect(dialog.getByText('第 2 / 2 页')).toBeVisible()
  await expect(dialog.getByRole('button', { name: '下一页' })).toBeDisabled()
  expect(await pixel()).toEqual([255, 0, 0, 255])
  expect(resources.some(url => /pdf.worker.*\.mjs/.test(url))).toBe(true)
  expect(errors).toEqual([])
  await page.screenshot({ path: test.info().outputPath('pdf-preview-page2.png'), fullPage: true })
})

test('预览失败显示原因且支持重试', async ({ page }) => {
  const requests = await setup(page, 'png', true)
  await page.getByRole('button', { name: '预览', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('alert')).toHaveText(/文件内容损坏/)
  await dialog.getByRole('button', { name: '重试', exact: true }).click()
  await expect(dialog.getByRole('img', { name: 'private.png' })).toBeVisible()
  expect(requests()).toBe(2)
})

test('加载中关闭取消请求，不残留图片或网络异常提示', async ({ page }) => {
  await setup(page, 'png', false, true)
  await page.getByRole('button', { name: '预览', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('status')).toBeVisible()
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await page.waitForTimeout(900)
  await expect(page.getByText('网络异常，请检查连接')).toHaveCount(0)
  await expect(page.locator('img[src^="blob:"]')).toHaveCount(0)
})

test('不支持的文件类型预览入口禁用', async ({ page }) => {
  const requests = await setup(page, 'svg')
  await expect(page.getByRole('button', { name: '预览', exact: true })).toBeDisabled()
  expect(requests()).toBe(0)
})

test('预览 401 使用共享刷新流程重放，令牌仍只在请求头', async ({ page }) => {
  const jwt = (marker: string) => `fixture.${Buffer.from(JSON.stringify({ sid: 'preview-session', user_id: 'member', session_version: 1, marker })).toString('base64url')}.fixture`
  const oldAccess = jwt('old'), oldRefresh = jwt('refresh-old'), newAccess = jwt('new'), newRefresh = jwt('refresh-new')
  await page.addInitScript(({ oldAccess, oldRefresh }) => {
    localStorage.setItem('token', oldAccess)
    localStorage.setItem('refreshToken', oldRefresh)
  }, { oldAccess, oldRefresh })
  await setup(page, 'png', false, false, oldAccess)
  let attempts = 0
  await page.route('**/api/v1/auth/refresh/', route => route.fulfill({ json: envelope({ access: newAccess, refresh: newRefresh }) }))
  await page.route('**/api/v1/files/f1/preview/', route => {
    attempts++
    if (attempts === 1) return route.fulfill({ status: 401, json: { code: 401, message: '认证失败', data: null } })
    expect(route.request().headers().authorization).toBe(`Bearer ${newAccess}`)
    expect(route.request().url()).not.toContain('token=')
    return route.fulfill({ contentType: 'image/png', body: png })
  })
  await page.getByRole('button', { name: '预览', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('img', { name: 'private.png' })).toBeVisible()
  expect(attempts).toBe(2)
  await expect(page).toHaveURL(/\/files$/)
})

test('英文暗色预览和图片解码失败可恢复，窄屏不溢出', async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') })
  await setup(page)
  let attempts = 0
  await page.route('**/api/v1/files/f1/preview/', route => {
    attempts++
    return route.fulfill({ contentType: 'image/png', body: attempts === 1 ? Buffer.from('broken image') : png })
  })
  await page.getByRole('button', { name: 'Preview', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('alert')).toHaveText(/Image preview failed/)
  await dialog.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(dialog.getByRole('img', { name: 'private.png' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('preview-dark-english.png'), fullPage: true })
})
