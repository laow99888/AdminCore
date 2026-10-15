/** 仅连接validate_codegen创建的入口；不读取正式管理员凭据。 */
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const [workspace, evidence] = process.argv.slice(2)
const require = createRequire(resolve(workspace, 'package.json'))
const { chromium, devices, expect } = require('@playwright/test')
const baseURL = 'http://127.0.0.1:18451'
const { password } = JSON.parse(readFileSync(resolve(evidence, 'browser-access.json'), 'utf8'))
const browser = await chromium.launch({ headless: true })
const checks = []
try {
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    const context = await browser.newContext({ ...device, baseURL })
    await context.tracing.start({ screenshots: true, snapshots: true })
    const page = await context.newPage()
    try {
      await page.goto('/login')
      await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
      await page.getByPlaceholder('密码', { exact: true }).fill(password)
      await page.getByRole('button', { name: '登录', exact: true }).click()
      await expect(page).toHaveURL(baseURL + '/')
      await page.goto('/work-assets')
      await expect(page.getByRole('heading', { name: '资产记录' })).toBeVisible()
      await expect(page.getByText('隔离资产', { exact: true })).toBeVisible()
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('页面溢出')
      await page.getByRole('row').filter({ hasText: '隔离资产' }).getByRole('button', { name: '编辑', exact: true }).click()
      const dialog = page.getByRole('dialog', { name: '资产记录', exact: true })
      await dialog.getByRole('textbox', { name: '名称', exact: true }).fill('保留未提交输入')
      // 由另一真实HTTP请求修改版本，浏览器保存必须得到409并保留输入。
      const token = await page.evaluate(() => localStorage.getItem('token'))
      const list = await context.request.get('/api/v1/work-assets/records/', { headers: { Authorization: 'Bearer ' + token } })
      const row = (await list.json()).data.items.find(item => item.label === '隔离资产')
      const changed = await context.request.patch('/api/v1/work-assets/records/' + row.id + '/', {
        headers: { Authorization: 'Bearer ' + token }, data: { version: row.version, quantity: row.quantity + 1 },
      })
      expect(changed.status()).toBe(200)
      const latest = (await changed.json()).data
      await dialog.getByRole('button', { name: '保存', exact: true }).click()
      await expect(dialog.getByRole('alert')).toContainText('输入已保留')
      await expect(dialog.getByRole('textbox', { name: '名称', exact: true })).toHaveValue('保留未提交输入')
      await page.screenshot({ path: resolve(evidence, 'generated-' + name + '-conflict.png'), fullPage: true })
      const panel = dialog.getByRole('region', { name: '编辑冲突' })
      await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeDisabled()
      await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
      await expect(panel.getByRole('table')).toContainText('隔离资产')
      await expect(panel.getByRole('table')).toContainText('保留未提交输入')
      await expect(panel.locator('tbody tr')).toHaveCount(4)
      for (const [label, local, server] of [
        ['名称', '保留未提交输入', latest.label], ['备注', row.remarks, latest.remarks],
        ['数量', String(row.quantity), String(latest.quantity)], ['可用', row.available ? '是' : '否', latest.available ? '是' : '否'],
      ]) {
        const comparison = panel.getByRole('row').filter({ has: page.getByRole('rowheader', { name: label, exact: true }) })
        await expect(comparison.getByRole('cell').nth(0)).toHaveText(local)
        await expect(comparison.getByRole('cell').nth(1)).toHaveText(server)
      }
      await expect(dialog.getByRole('textbox', { name: '名称', exact: true })).toHaveValue('保留未提交输入')
      await expect(panel).toContainText('服务器版本：' + latest.version)
      await panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click()
      await expect(panel).toHaveCount(0)
      await expect(dialog.getByRole('textbox', { name: '名称', exact: true })).toHaveValue('隔离资产')
      const savedRequest = page.waitForRequest(request => request.method() === 'PATCH' && request.url().endsWith('/work-assets/records/' + row.id + '/'))
      await dialog.getByRole('button', { name: '保存', exact: true }).click()
      expect((await savedRequest).postDataJSON().version).toBe(latest.version)
      await expect(dialog).toHaveCount(0)
      const persisted = await context.request.get('/api/v1/work-assets/records/' + row.id + '/', { headers: { Authorization: 'Bearer ' + token } })
      expect((await persisted.json()).data.version).toBe(latest.version + 1)
      await page.getByRole('row').filter({ hasText: '隔离资产' }).getByRole('button', { name: '详情', exact: true }).click()
      await expect(page.getByRole('dialog').getByText('<script>正文只作文字</script>', { exact: true })).toBeVisible()
      expect(await page.evaluate(() => document.querySelector('script')?.textContent?.includes('正文只作文字') ?? false)).toBe(false)
      await page.getByRole('dialog').getByRole('button', { name: '关闭', exact: true }).click()
      // 新建界面包含所有生成字段；双击只发送一次，服务器也只创建一行。
      await page.getByRole('button', { name: '新增', exact: true }).click()
      await page.getByRole('dialog').getByRole('textbox', { name: '名称', exact: true }).fill('浏览器新增-' + name)
      await page.getByRole('dialog').getByRole('textbox', { name: '备注', exact: true }).fill('新建草稿')
      await page.getByRole('dialog').getByRole('button', { name: '保存', exact: true }).dblclick()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(page.getByText('浏览器新增-' + name, { exact: true })).toBeVisible()
      const after = await context.request.get('/api/v1/work-assets/records/', { headers: { Authorization: 'Bearer ' + token } })
      expect((await after.json()).data.items.filter(item => item.label === '浏览器新增-' + name)).toHaveLength(1)
      await page.screenshot({ path: resolve(evidence, 'generated-' + name + '-list.png'), fullPage: true })
      checks.push(name + ': real sign-in, bound fields, version conflict/input retention/server comparison/explicit apply/current-version save, escaped details, create')
      await context.tracing.stop()
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, 'generated-' + name + '-failure.png'), fullPage: true })
      await context.tracing.stop({ path: resolve(evidence, 'generated-' + name + '-failure.zip') })
      throw error
    } finally {
      await context.close()
    }
  }
  writeFileSync(resolve(evidence, 'browser-report.json'), JSON.stringify({ passed: true, checks }, null, 2))
} finally {
  await browser.close()
}
