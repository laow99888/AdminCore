/** 对隔离的真实精简/完整镜像进行浏览器验收，不读取正式管理员凭据。 */
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const [frontend, evidence, mode] = process.argv.slice(2)
const require = createRequire(resolve(frontend, 'package.json'))
const { chromium, devices, expect } = require('@playwright/test')
const { password } = JSON.parse(readFileSync(resolve(evidence, 'browser-access.json'), 'utf8'))
const origin = 'http://127.0.0.1:18481'
const checks = []
const browser = await chromium.launch({ headless: true })
try {
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    const context = await browser.newContext({ ...device, baseURL: origin })
    await context.tracing.start({ screenshots: true, snapshots: true })
    const page = await context.newPage()
    const errors = [], assets = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (/\.js(?:\?|$)/.test(request.url())) assets.push(request.url()) })
    try {
      expect((await (await page.request.get('/build-profile.json')).json()).profile).toBe(mode === 'mismatch' ? 'minimal' : mode)
      await page.goto('/login')
      await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
      await page.getByPlaceholder('密码', { exact: true }).fill(password)
      let loggedIn = false
      for (let attempt = 0; attempt < 2; attempt++) {
        const event = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/login/') && response.request().method() === 'POST')
        await page.getByRole('button', { name: '登录', exact: true }).click()
        const response = await event
        if (response.status() !== 429) { expect(response.status()).toBe(200); loggedIn = true; break }
        const seconds = Number(response.headers()['retry-after'])
        expect(Number.isFinite(seconds) && seconds > 0 && seconds <= 65).toBe(true)
        await page.waitForTimeout(Math.ceil(seconds * 1000) + 100)
      }
      expect(loggedIn).toBe(true)
      if (mode === 'mismatch') {
        await expect(page).toHaveURL(origin + '/unavailable')
        await expect(page.locator('.service-error')).toBeVisible()
        await expect(page.getByText('精简前端无法加载已启用的可选模块，请同步重新构建完整前后端镜像', { exact: true })).toBeVisible()
        expect(errors).toEqual([])
        await page.screenshot({ path: resolve(evidence, `minimal-build-${mode}-${name}.png`), fullPage: true })
        checks.push(`${mode}/${name}: incompatible module contract fails visibly before module loading`)
        await context.tracing.stop()
        continue
      }
      await expect(page).toHaveURL(origin + '/')
      for (const path of ['/users', '/roles', '/menus', '/logs']) {
        await page.goto(path)
        await expect(page.locator('.el-table__body-wrapper')).toBeVisible()
        const exportButton = page.getByRole('button', { name: '本地 Excel（当前页）', exact: true })
        if (mode === 'minimal') await expect(exportButton).toHaveCount(0)
        else if (path !== '/menus') await expect(exportButton).toBeEnabled()
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      }
      if (mode === 'minimal') {
        expect(assets.every(url => !/pdf-preview|pdf\.worker|localWorkbook\.worker|WorkItemListView|FileListView|ApprovalListView|TaskListView|AnnouncementView/.test(url))).toBe(true)
        // 路由被编译掉后，直接访问落入404页；不会加载模块页面。
        await page.goto('/files')
        await expect(page.locator('.not-found-container')).toBeVisible()
        for (const asset of ['/pdf-assets/LICENSE', '/third-party/sheetjs/LICENSE']) {
          // SPA回退可能是200；必须不会返回对应依赖的许可证内容。
          expect(await (await page.request.get(asset)).text()).not.toContain('Apache License')
        }
      } else {
        await page.goto('/files')
        await expect(page.locator('.el-table__body-wrapper')).toBeVisible()
        await expect(page.getByText('retained.txt', { exact: true })).toBeVisible()
        await expect(page.getByRole('button', { name: '本地 Excel（当前页）', exact: true })).toBeEnabled()
        expect(await (await page.request.get('/pdf-assets/LICENSE')).text()).toContain('Apache License')
      }
      expect(errors).toEqual([])
      await page.screenshot({ path: resolve(evidence, `minimal-build-${mode}-${name}.png`), fullPage: true })
      checks.push(`${mode}/${name}: real login, core lists, bounded layout, capability assets and routes`)
      await context.tracing.stop()
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, `minimal-build-${mode}-${name}-failure.png`), fullPage: true })
      await context.tracing.stop({ path: resolve(evidence, `minimal-build-${mode}-${name}-failure.zip`) })
      throw error
    } finally { await context.close() }
  }
  writeFileSync(resolve(evidence, `browser-${mode}-report.json`), JSON.stringify({ passed: true, checks }, null, 2))
} finally { await browser.close() }
