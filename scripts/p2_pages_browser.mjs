/** 真实产品页面/SQL/API；失败 trace 私有保留，报告只包含用例名称。 */
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const [frontend, evidence, port] = process.argv.slice(2)
const { chromium, devices, expect } = createRequire(resolve(frontend, 'package.json'))('@playwright/test')
const { password, users } = JSON.parse(readFileSync(resolve(evidence, 'browser-access.json'), 'utf8'))
const origin = `http://127.0.0.1:${port}`, browser = await chromium.launch({ headless: true })
const checks = [], failures = [], diagnostics = []
let stage = 'login'
const response = (page, path, method) => page.waitForResponse(res => new URL(res.url()).pathname === '/api/v1/' + path && res.request().method() === method)
async function choose(page, label, option) {
  await page.locator('.el-select').filter({ has: page.getByRole('combobox', { name: label, exact: true }) }).locator('.el-select__wrapper').click()
  await page.getByRole('option', { name: option, exact: true }).click()
}
async function flow(page, name) {
  await page.goto('/approvals/flows')
  await page.getByRole('button', { name: '新建草稿', exact: true }).click()
  await page.getByRole('textbox', { name: '流程名称', exact: true }).fill(name + '流程')
  await page.getByRole('textbox', { name: '流程编码', exact: true }).fill(name + '-flow')
  const nodes = page.locator('.editor-card .el-table').first()
  await nodes.locator('tbody tr').nth(1).getByRole('textbox').last().fill(users[name])
  const saved = response(page, 'approvals/flows/', 'POST')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  const row = await (await saved).json()
  expect(row.data.id).toBeTruthy()
  const published = response(page, `approvals/flows/${row.data.id}/publish/`, 'POST')
  await page.getByRole('button', { name: '发布', exact: true }).click()
  expect((await published).status()).toBe(200)
  await expect(page.getByRole('button', { name: '保存草稿', exact: true })).toBeDisabled()
  await expect(page.getByRole('textbox', { name: '流程名称', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '添加节点', exact: true })).toBeDisabled()
  await page.reload()
  await page.getByText(name + '流程', { exact: true }).click()
  await expect(page.getByRole('textbox', { name: '流程编码', exact: true })).toHaveValue(name + '-flow')
  await expect(page.getByRole('button', { name: '保存草稿', exact: true })).toBeDisabled()
}
async function online(page, name) {
  await page.goto('/online-forms')
  await page.getByRole('button', { name: '新建草稿', exact: true }).click()
  await page.getByRole('textbox', { name: '名称', exact: true }).fill(name + '表单')
  await page.getByRole('textbox', { name: '编码', exact: true }).fill(name + '-form')
  const saved = response(page, 'online-forms/forms/', 'POST')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  const row = await (await saved).json()
  expect(row.data.id).toBeTruthy()
  const published = response(page, `online-forms/forms/${row.data.id}/publish/`, 'POST')
  await page.getByRole('button', { name: '发布', exact: true }).click()
  expect((await published).status()).toBe(200)
  await expect(page.getByRole('button', { name: '保存草稿', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '添加字段', exact: true })).toBeDisabled()
  await expect(page.locator('.el-table').last().getByRole('textbox').first()).toBeDisabled()
  await page.goto('/online-forms/' + name + '-form')
  await expect(page.getByLabel('标题', { exact: true })).toBeVisible()
  const invalid = response(page, `online-forms/${name}-form/records/`, 'POST')
  await page.getByRole('button', { name: '提交', exact: true }).click()
  expect((await invalid).status()).toBe(400)
  await expect(page.locator('.el-message--error')).toHaveCount(1)
  await page.getByLabel('标题', { exact: true }).fill('实际填写')
  const submitted = response(page, `online-forms/${name}-form/records/`, 'POST')
  await page.getByRole('button', { name: '提交', exact: true }).click()
  expect((await submitted).status()).toBe(201)
  await expect(page.getByLabel('标题', { exact: true })).toHaveValue('')
  await expect(page.getByText('提交成功', { exact: true })).toBeVisible()
  await expect(page.locator('.el-message--error')).toHaveCount(0)
}
async function report(page, name) {
  stage = 'report-open-and-configure'
  await page.goto('/reports')
  await page.getByRole('textbox', { name: '名称', exact: true }).fill(name + '报表')
  await page.getByRole('textbox', { name: '编码', exact: true }).fill(name + '-report')
  await choose(page, '图表', 'bar')
  await choose(page, '维度', 'status')
  stage = 'report-save'
  const saved = response(page, 'reports/definitions/', 'POST')
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  const row = await (await saved).json()
  expect(row.data.id).toBeTruthy()
  await expect(page.getByText('已保存', { exact: true })).toBeVisible()
  await expect(page.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '维度', exact: true }) })).toContainText('status')
  stage = 'report-publish'
  const published = response(page, `reports/definitions/${row.data.id}/publish/`, 'POST')
  const publishButton = page.getByRole('button', { name: '发布', exact: true })
  const runButton = page.getByRole('row').filter({ hasText: name + '报表' }).getByRole('button', { name: '运行', exact: true })
  await expect(publishButton).toBeEnabled()
  // 只暂停真实目录请求，不伪造响应；使发布后的重载窗口可确定地观察。
  let resumeCatalog
  const catalogGate = new Promise(resolve => { resumeCatalog = resolve })
  const catalogRoute = async route => { await catalogGate; await route.continue() }
  const reloadRequest = page.waitForRequest(req => new URL(req.url()).pathname === '/api/v1/reports/catalog/')
  await page.route('**/api/v1/reports/catalog/', catalogRoute)
  try {
    await publishButton.click()
    expect((await published).status()).toBe(200)
    await reloadRequest
    stage = 'report-busy-run-disabled'
    await expect(runButton).toBeDisabled()
    await expect(publishButton).toBeDisabled()
    await expect(page.getByRole('button', { name: '保存草稿', exact: true })).toBeDisabled()
  } finally {
    resumeCatalog()
    await page.unrouteAll({ behavior: 'wait' })
  }
  await expect(runButton).toBeEnabled()
  stage = 'report-run'
  const ran = response(page, `reports/definitions/${row.data.id}/run/`, 'GET')
  await runButton.click()
  const data = (await (await ran).json()).data
  expect(data.rows).toEqual([{ status: 'pending', value: 2 }, { status: 'success', value: 1 }])
  stage = 'report-chart-and-data'
  await expect(page.locator('.result')).toContainText('pending')
  await expect(page.locator('.base-chart canvas')).toBeVisible()
  await page.getByText('查看图表数据', { exact: true }).click()
  await expect(page.locator('.chart-data table')).toContainText('pending')
  stage = 'report-reload-and-select'
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.reload()
    await page.getByRole('row').filter({ hasText: name + '报表' }).click()
    await expect(page.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '维度', exact: true }) })).toContainText('status')
    await expect(page.getByRole('button', { name: '保存草稿', exact: true })).toBeDisabled()
  }
}
try {
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    for (const [feature, action] of [['flow', flow], ['form', online], ['report', report]]) {
      const context = await browser.newContext({ ...device, baseURL: origin })
      await context.tracing.start({ screenshots: true, snapshots: true })
      const page = await context.newPage(), errors = [], disabledModuleRequests = []
      page.on('response', res => { if (res.status() === 404 && new URL(res.url()).pathname === '/api/v1/organization/my-tenants/') disabledModuleRequests.push('organization/my-tenants') })
      page.on('pageerror', error => errors.push(error.message))
      page.on('console', message => { if (message.type() === 'error' && message.text().includes('[ECharts]')) errors.push(message.text()) })
      try {
        stage = 'login'
        await page.goto('/login')
        await page.getByPlaceholder('用户名', { exact: true }).fill(name === 'desktop' ? 'admin' : 'mobile-admin')
        await page.getByPlaceholder('密码', { exact: true }).fill(password)
        await page.getByRole('button', { name: '登录', exact: true }).click()
        await expect(page.locator('.dashboard-container')).toBeVisible()
        stage = feature + '-actions'
        await action(page, name)
        stage = 'page-errors'
        expect(errors).toEqual([])
        stage = 'disabled-module-requests'
        expect(disabledModuleRequests).toEqual([])
        stage = 'layout-overflow'
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        await page.screenshot({ path: resolve(evidence, `${name}-${feature}.png`), fullPage: true })
        checks.push(`${name}: ${feature} 实际创建/发布/交互、布局、无页面异常`)
        await context.tracing.stop()
      } catch (error) {
        failures.push(name + '-' + feature)
        diagnostics.push({ case: name + '-' + feature, stage, error: error?.name || 'Error' })
        await page.screenshot({ path: resolve(evidence, `${name}-${feature}-failure.png`), fullPage: true })
        await context.tracing.stop({ path: resolve(evidence, `${name}-${feature}-failure.zip`) })
        process.stderr.write(String(error) + '\n')
      } finally { await context.close() }
    }
  }
  writeFileSync(resolve(evidence, 'browser-report.json'), JSON.stringify({ passed: !failures.length, checks, failures, diagnostics }, null, 2))
  if (failures.length) throw new Error('P2 browser cases failed: ' + failures.join(', '))
} finally { await browser.close() }
