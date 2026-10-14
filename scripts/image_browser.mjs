/** 只使用 validate_images 创建的真实入口和临时密码。 */
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const [frontend, evidence] = process.argv.slice(2)
const { chromium, devices, expect } = createRequire(resolve(frontend, 'package.json'))('@playwright/test')
const { password } = JSON.parse(readFileSync(resolve(evidence, 'browser-access.json'), 'utf8'))
const browser = await chromium.launch({ headless: true })
const checks = []
try {
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    const context = await browser.newContext({ ...device, baseURL: 'http://127.0.0.1:18461' })
    await context.tracing.start({ screenshots: true, snapshots: true })
    const page = await context.newPage()
    try {
      await page.goto('/login')
      await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
      await page.getByPlaceholder('密码', { exact: true }).fill(password)
      await page.getByRole('button', { name: '登录', exact: true }).click()
      await expect(page).toHaveURL('http://127.0.0.1:18461/')
      await page.goto('/files')
      await page.getByRole('button', { name: '图片处理', exact: true }).click()
      const dialog = page.getByRole('dialog', { name: '图片处理', exact: true })
      await dialog.getByRole('spinbutton', { name: '最大宽度（px）', exact: true }).fill('80')
      await dialog.getByRole('spinbutton', { name: '最大高度（px）', exact: true }).fill('80')
      const png = Buffer.from(await page.evaluate(() => {
        const canvas = document.createElement('canvas'); canvas.width = 20; canvas.height = 20
        const drawing = canvas.getContext('2d'); drawing.fillStyle = 'red'; drawing.fillRect(0, 0, 20, 20)
        return canvas.toDataURL('image/png').split(',')[1]
      }), 'base64')
      await dialog.locator('input[type="file"]').setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: png })
      await dialog.getByRole('button', { name: '生成预览', exact: true }).click()
      const image = dialog.getByRole('img', { name: '处理结果预览', exact: true })
      await expect(image).toBeVisible()
      await expect.poll(() => image.evaluate(element => [element.naturalWidth, element.naturalHeight])).toEqual([80, 53])
      const downloaded = page.waitForEvent('download')
      await dialog.getByRole('button', { name: '下载处理结果', exact: true }).click()
      expect((await downloaded).suggestedFilename()).toBe('processed.webp')
      const bounds = await dialog.boundingBox()
      expect(bounds.x).toBeGreaterThanOrEqual(0)
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(page.viewportSize().width)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({ path: resolve(evidence, 'images-' + name + '.png'), fullPage: true })
      await dialog.getByRole('button', { name: '取消', exact: true }).click()
      await expect(page.getByRole('dialog', { name: '提示', exact: true })).toBeVisible()
      await page.getByRole('dialog', { name: '提示', exact: true }).getByRole('button', { name: '取消', exact: true }).click()
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: '取消', exact: true }).click()
      await page.getByRole('dialog', { name: '提示', exact: true }).getByRole('button', { name: '确定', exact: true }).click()
      await expect(dialog).toBeHidden()
      await expect(page.locator('img[src^="blob:"]')).toHaveCount(0)
      checks.push(name + ': real login, resize, uploaded watermark, download, bounded layout, discard guard')
      await context.tracing.stop()
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, 'images-' + name + '-failure.png'), fullPage: true })
      await context.tracing.stop({ path: resolve(evidence, 'images-' + name + '-failure.zip') })
      throw error
    } finally { await context.close() }
  }
  writeFileSync(resolve(evidence, 'browser-report.json'), JSON.stringify({ passed: true, checks }, null, 2))
} finally { await browser.close() }
