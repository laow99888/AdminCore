import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const csp = readFileSync('spa-csp.conf', 'utf8').match(/Content-Security-Policy "([^"]+)"/)![1]
function pdfFixture() {
  const stream = '0 0 1 rg 0 0 200 300 re f'
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Resources << >> /Contents 4 0 R >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`]
  let text = '%PDF-1.4\n'
  const offsets = [0]
  for (let i = 0; i < objects.length; i++) {
    offsets.push(Buffer.byteLength(text)); text += `${i + 1} 0 obj\n${objects[i]}\nendobj\n`
  }
  const start = Buffer.byteLength(text)
  text += `xref\n0 5\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n${start}\n%%EOF\n`
  return Buffer.from(text)
}

async function setup(page: Page, { enabled = true, pending = false, failure = false } = {}) {
  const counts = { submitted: 0, polled: 0, cancelled: 0, pdf: 0 }
  await page.addInitScript(() => localStorage.setItem('token', 'office-ui-fixture'))
  await page.route('**/files', async route => {
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': csp } })
  })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'member', username: 'member', permissions: ['file:download'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'files', title: 'Files', enabled: true, paths: ['/files'], dependencies: [] }] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/files/')) return route.fulfill({ json: envelope({ items: [{ id: 'f1', original_name: 'private.docx', file_type: 'docx', lifecycle_version: 7, size: 500, size_display: '500 B' }], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } }) })
    if (path.endsWith('/office-preview/config/')) return route.fulfill({ json: envelope({ enabled }) })
    if (path.endsWith('/office-preview/')) {
      counts.submitted++
      expect(route.request().headers().authorization).toBe('Bearer office-ui-fixture')
      expect(route.request().headers()['idempotency-key']).toBeTruthy()
      expect(route.request().postDataJSON()).toEqual({ lifecycle_version: 7 })
      return route.fulfill({ status: 202, json: envelope({ id: 'job1', status: 'pending', error: '', expires_at: '' }) })
    }
    if (path.endsWith('/jobs/job1/pdf/')) {
      counts.pdf++
      expect(route.request().headers().authorization).toBe('Bearer office-ui-fixture')
      expect(route.request().url()).not.toContain('token=')
      return route.fulfill({ contentType: 'application/pdf', body: pdfFixture() })
    }
    if (path.endsWith('/jobs/job1/')) {
      if (route.request().method() === 'DELETE') counts.cancelled++
      else counts.polled++
      return route.fulfill({ json: envelope({ id: 'job1', status: failure ? 'failed' : pending ? 'running' : 'success', error: failure ? 'conversion_failed' : '', expires_at: '' }) })
    }
    return route.fulfill({ json: envelope({ enabled: false, count: 0 }) })
  })
  await page.goto('/files')
  return counts
}

test('默认关闭使 Office 入口禁用', async ({ page }) => {
  const counts = await setup(page, { enabled: false })
  await expect(page.getByRole('button', { name: '预览', exact: true })).toBeDisabled()
  expect(counts.submitted).toBe(0)
})

test('Office 轮询后使用生产 CSP 下的真实 PDF worker 绘制，窄屏可读', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const counts = await setup(page)
  await page.getByRole('button', { name: '预览', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('status')).toContainText('安全转换')
  await expect(dialog.getByText('第 1 / 1 页')).toBeVisible()
  await expect(dialog.getByRole('status')).toHaveCount(0)
  expect(await dialog.locator('canvas').evaluate((element: HTMLCanvasElement) => [...element.getContext('2d')!.getImageData(5, 5, 1, 1).data])).toEqual([0, 0, 255, 255])
  expect(counts.submitted).toBe(1); expect(counts.pdf).toBe(1)
  expect(errors).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('office-preview-canvas.png'), fullPage: true })
})

test('关闭轮询中预览提交取消，迟到结果不再加载', async ({ page }) => {
  const counts = await setup(page, { pending: true })
  await page.getByRole('button', { name: '预览', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('status')).toBeVisible()
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect.poll(() => counts.cancelled).toBe(1)
  const before = counts.polled
  await page.waitForTimeout(1700)
  expect(counts.polled).toBe(before); expect(counts.pdf).toBe(0)
  await expect(page.locator('canvas')).toHaveCount(0)
})

test('转换失败可读且不下载错误内容', async ({ page }) => {
  const counts = await setup(page, { failure: true })
  await page.getByRole('button', { name: '预览', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('alert')).toContainText('转换失败')
  await expect(dialog.getByRole('button', { name: '重试', exact: true })).toBeEnabled()
  expect(counts.pdf).toBe(0)
})
