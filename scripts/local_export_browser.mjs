/** 仅访问验收脚本的真实入口，不读取正式密码。 */
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const [frontend, evidence, mode] = process.argv.slice(2)
const require = createRequire(resolve(frontend, 'package.json'))
const { chromium, devices, expect } = require('@playwright/test')
const { read, utils } = require('xlsx')
const { password } = JSON.parse(readFileSync(resolve(evidence, 'browser-access.json'), 'utf8'))
const browser = await chromium.launch({ headless: true })
const checks = []
try {
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    const context = await browser.newContext({ ...device, baseURL: 'http://127.0.0.1:18471' })
    await context.tracing.start({ screenshots: true, snapshots: true })
    const page = await context.newPage()
    try {
      await page.goto('/login')
      await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
      await page.getByPlaceholder('密码', { exact: true }).fill(password)
      await page.getByRole('button', { name: '登录', exact: true }).click()
      await expect(page).toHaveURL('http://127.0.0.1:18471/')
      let exports = 0
      page.on('request', request => { if (request.url().includes('/data-io/export/')) exports++ })
      for (const [path, resource] of [['/users', 'users'], ['/roles', 'roles'], ['/files', 'files'], ['/logs', 'logs']]) {
        await page.goto(path)
        await expect(page.locator('.el-table__body-wrapper')).toBeVisible()
        const button = page.getByRole('button', { name: '本地 Excel（当前页）', exact: true })
        if (mode === 'off') { await expect(button).toHaveCount(0); continue }
        await expect(button).toBeEnabled()
        const event = page.waitForEvent('download')
        await button.click()
        const download = await event
        expect(download.suggestedFilename()).toBe(resource + '-page-1.xlsx')
        const target = resolve(evidence, `${mode}-${name}-${resource}.xlsx`)
        await download.saveAs(target)
        const workbook = read(readFileSync(target), { type: 'buffer' })
        const data = utils.sheet_to_json(workbook.Sheets.Data, { header: 1 })
        expect(data.length).toBeGreaterThan(1)
        if (resource === 'users') {
          const member = data.find(row => row[0] === 'local_export_member')
          expect(member).toBeTruthy(); expect(member[1]).toContain('*'); expect(member[2]).toContain('*')
          expect(JSON.stringify(data)).not.toContain('member-private@example.test')
          expect(JSON.stringify(data)).not.toContain('13912345678')
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        await expect(button).toBeEnabled()
      }
      expect(exports).toBe(0)
      await page.screenshot({ path: resolve(evidence, `local-export-${mode}-${name}.png`), fullPage: true })
      checks.push(`${name}: ${mode}, real login and four lists; no server export; bounded layout`)
      await context.tracing.stop()
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, `local-export-${mode}-${name}-failure.png`), fullPage: true })
      await context.tracing.stop({ path: resolve(evidence, `local-export-${mode}-${name}-failure.zip`) })
      throw error
    } finally { await context.close() }
  }
  writeFileSync(resolve(evidence, `browser-${mode}-report.json`), JSON.stringify({ passed: true, checks }, null, 2))
} finally { await browser.close() }
