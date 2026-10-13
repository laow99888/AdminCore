import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const information = { sampled_at: '2026-10-14T00:00:00+08:00', python: '3.13.15', os: 'Linux', architecture: 'x86_64', environment: 'production', debug: false, preset: 'standard', modules: ['system', 'tasks'], timezone: 'Asia/Shanghai', database: 'postgresql', storage: 'local', dependencies: [{ name: 'Django', version: '5.2.18' }, { name: 'gunicorn', version: null }], services: [{ name: 'database', status: 'ok', version: '18.6', latency_ms: 1.2 }, { name: 'cache', status: 'unavailable', version: null, latency_ms: null }, { name: 'broker', status: 'disabled', version: null, latency_ms: null }] }
const resources = { sampled_at: information.sampled_at, scope: 'container', cpu: { capacity_cores: 2, percent: 25, sample_seconds: 0.12 }, memory: { used_bytes: 104857600, total_bytes: null, percent: null }, disks: [{ name: 'media', status: 'ok', used_bytes: 1024, total_bytes: 4096, free_bytes: 3072, percent: 25 }], processes: [{ pid: 1, kind: 'python', state: 'S', cpu_seconds: 3.5, rss_bytes: 10485760, uptime_seconds: 600 }], processes_supported: true, processes_truncated: false }

async function setup(page: Page, options: { member?: boolean; disabled?: boolean; english?: boolean } = {}) {
  await page.addInitScript(({ english }) => { localStorage.setItem('token', 'isolated-diagnostics-fixture'); if (english) { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') } }, options)
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'admin', username: 'admin', is_staff: !options.member, is_superuser: !options.member, permissions: ['*'] }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'system', title: '系统管理', paths: ['/system/information', '/system/monitor'], dependencies: [], enabled: !options.disabled }] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/system/information/')) return route.fulfill({ json: envelope(information) })
    if (path.endsWith('/system/monitor/')) return route.fulfill({ json: envelope(resources) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    return route.fulfill({ json: envelope({ count: 0, totals: {}, login_trend: [], task_status: {} }) })
  })
}

test('系统信息显示真实版本、部分故障和未安装，桌面手机可读', async ({ page }, info) => {
  await setup(page)
  await page.goto('/system/information')
  await expect(page.getByRole('heading', { name: '系统信息' })).toBeVisible()
  await expect(page.getByText('3.13.15', { exact: true })).toBeVisible()
  await expect(page.getByText('5.2.18', { exact: true })).toBeVisible()
  await expect(page.getByText('不可用', { exact: true })).toBeVisible()
  await expect(page.getByText('未安装', { exact: true })).toBeVisible()
  await expect(page.locator('.service .el-tag').first()).not.toHaveClass(/enter-active|enter-from/)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('system-information.png'), fullPage: true })
})

test('资源显示容器口径、未知内存上限和累计进程 CPU，窄屏无溢出', async ({ page }, info) => {
  await setup(page)
  await page.goto('/system/monitor')
  await expect(page.getByRole('heading', { name: '服务监控' })).toBeVisible()
  await expect(page.getByText('25.00%', { exact: true })).toBeVisible()
  await expect(page.getByText('未采集或未设置上限')).toBeVisible()
  await expect(page.getByText('PID 1 · Python', { exact: true })).toBeVisible()
  await expect(page.getByText('3.5 s', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('system-monitor.png'), fullPage: true })
})

test('刷新加载禁用重复点击，错误清除旧样本并可恢复', async ({ page }) => {
  await setup(page)
  await page.goto('/system/information')
  await expect(page.getByText('3.13.15', { exact: true })).toBeVisible()
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  await page.route('**/system/information/', async route => { await held; return route.fulfill({ status: 503, json: envelope(null) }) })
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('button', { name: '刷新', exact: true })).toBeDisabled()
  await expect(page.getByText('3.13.15', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('正在采集诊断信息')
  release()
  await expect(page.getByRole('alert').filter({ hasText: '诊断信息加载失败' })).toBeVisible()
  await page.route('**/system/information/', route => route.fulfill({ json: envelope(information) }))
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByText('3.13.15', { exact: true })).toBeVisible()
})

test('不支持采集和空进程明确展示，不伪造零使用率', async ({ page }) => {
  await setup(page)
  await page.route('**/system/monitor/', route => route.fulfill({ json: envelope({ ...resources, cpu: { capacity_cores: null, percent: null, sample_seconds: null }, memory: { used_bytes: null, total_bytes: null, percent: null }, processes: [], processes_supported: false, processes_truncated: true }) }) )
  await page.goto('/system/monitor')
  await expect(page.getByText('当前平台不支持进程采集', { exact: true })).toBeVisible()
  await expect(page.getByText('进程列表已截断', { exact: true })).toBeVisible()
  await expect(page.getByText('未采集', { exact: true }).first()).toBeVisible()
  await page.route('**/system/monitor/', route => route.fulfill({ json: envelope({ ...resources, processes: [] }) }))
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByText('暂无可见进程', { exact: true })).toBeVisible()
})

test('普通成员禁止访问，关闭模块撤下页面', async ({ page }) => {
  await setup(page, { member: true })
  await page.goto('/system/information')
  await expect(page).toHaveURL(/\/403$/)
  await setup(page, { disabled: true })
  await page.goto('/system/monitor')
  await expect(page).toHaveURL(/\/$/)
})

test('英文深色模式与键盘刷新可用', async ({ page }, info) => {
  await setup(page, { english: true })
  await page.goto('/system/monitor')
  await expect(page.getByRole('heading', { name: 'Service Monitor' })).toBeVisible()
  await expect(page.getByText('Unavailable or no limit configured')).toBeVisible()
  await page.getByRole('button', { name: 'Refresh', exact: true }).focus()
  const request = page.waitForRequest(req => req.url().endsWith('/system/monitor/'))
  await page.keyboard.press('Enter')
  await request
  await expect(page.getByText('PID 1 · Python', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('monitor-dark-en.png'), fullPage: true })
})
