/** 真实 HTTPS 身份源、PKCE/RSA 和产品 Cookie 登录；成功报告不含令牌或回调 URL。 */
import { createRequire } from 'node:module'
import { writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const [frontend, evidence, port, providerPort, selected] = process.argv.slice(2)
if (!['desktop', 'mobile'].includes(selected)) throw new Error('Specify an isolated desktop or mobile suite')
const { chromium, devices, expect } = createRequire(resolve(frontend, 'package.json'))('@playwright/test')
const origin = `https://127.0.0.1:${port}`, issuer = `https://127.0.0.1:${providerPort}`
const browser = await chromium.launch({ headless: true })
const checks = []
async function noPersistence(page) {
  expect(await page.evaluate(() => [localStorage.getItem('token'), localStorage.getItem('refreshToken'),
    sessionStorage.getItem('token'), sessionStorage.getItem('refreshToken')])).toEqual([null, null, null, null])
  expect(await page.evaluate(() => document.cookie)).not.toContain('admincore_refresh')
}
try {
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    if (name !== selected) continue
    const context = await browser.newContext({ ...device, baseURL: origin, ignoreHTTPSErrors: true })
    await context.addInitScript(() => {
      window.__fixtureSnapshots = 0
      window.addEventListener('admincore:realtime-snapshot', () => { window.__fixtureSnapshots++ })
    })
    await context.tracing.start({ screenshots: true, snapshots: true })
    const page = await context.newPage(), errors = []
    page.on('pageerror', error => errors.push(error.message))
    try {
      for (const choice of ['取消授权', '未绑定成员']) {
        await page.goto('/enterprise-login')
        await page.getByRole('button', { name: '前往企业认证', exact: true }).click()
        await expect(page.getByRole('heading', { name: '隔离身份源', exact: true })).toBeVisible()
        expect(new URL(page.url()).origin).toBe(issuer)
        await page.getByRole('button', { name: choice, exact: true }).click()
        await expect(page).toHaveURL(origin + '/enterprise-login?result=failed')
        await expect(page.getByRole('alert')).toContainText('企业身份授权未完成')
        expect((await context.cookies()).some(item => item.name === '__Host-admincore_refresh')).toBe(false)
        await noPersistence(page)
      }
      checks.push(name + ': 真实身份源取消及未绑定身份拒绝，未签发本地会话')
      await page.goto('/enterprise-login')
      await page.getByRole('button', { name: '前往企业认证', exact: true }).click()
      await expect(page.getByRole('heading', { name: '隔离身份源', exact: true })).toBeVisible()
      const callbackResponse = page.waitForResponse(res => new URL(res.url()).pathname === '/api/v1/sso/callback/')
      await page.getByRole('button', { name: name === 'desktop' ? '桌面验收成员' : '手机验收成员', exact: true }).click()
      const callback = await callbackResponse, callbackUrl = callback.url()
      expect(callback.status()).toBe(302)
      await expect(page).toHaveURL(origin + '/enterprise-login?result=ready')
      const completion = (await context.cookies()).find(item => item.name === 'admincore_sso_completion')
      expect(completion).toMatchObject({ httpOnly: true, secure: true, sameSite: 'Lax', path: '/api/v1/sso/' })
      expect((await context.cookies()).some(item => item.name === '__Host-admincore_refresh')).toBe(false)
      const completed = page.waitForResponse(res => res.url().endsWith('/sso/complete/') && res.request().method() === 'POST')
      await page.getByRole('button', { name: '验证并登录', exact: true }).click()
      const response = await completed, result = (await response.json()).data
      expect(response.status()).toBe(200)
      expect(result.session_transport).toBe('cookie'); expect(result.refresh).toBeUndefined()
      expect(JSON.parse(Buffer.from(result.access.split('.')[1], 'base64url').toString('utf8')).sso).toBe(true)
      await expect(page).toHaveURL(origin + '/')
      await expect(page.locator('.dashboard-container')).toBeVisible()
      const cookie = (await context.cookies()).find(item => item.name === '__Host-admincore_refresh')
      expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: 'Lax', path: '/' })
      expect((await context.cookies()).some(item => item.name === 'admincore_sso_completion')).toBe(false)
      const user = await context.request.get(origin + '/api/v1/auth/me/', { headers: { Authorization: 'Bearer ' + result.access } })
      expect(user.status()).toBe(200); expect((await user.json()).data.username).toBe('sso-' + name)
      await noPersistence(page)
      checks.push(name + ': HTTPS授权码与PKCE/RSA校验、绑定本地身份、一次确认及Host HttpOnly Cookie')
      const replay = await context.request.post(origin + '/api/v1/sso/complete/', {
        headers: { Origin: origin, 'X-AdminCore-Session': 'cookie', 'X-CSRFToken': result.csrf_token }, data: {},
      })
      expect(replay.status()).toBe(401)
      await expect.poll(() => page.evaluate(() => window.__fixtureSnapshots)).toBeGreaterThan(0)
      await page.reload(); await expect(page.locator('.dashboard-container')).toBeVisible(); await noPersistence(page)
      const second = await context.newPage()
      await second.goto('/'); await expect(second.locator('.dashboard-container')).toBeVisible()
      await Promise.all([page.reload(), second.reload()])
      await expect(page.locator('.dashboard-container')).toBeVisible()
      await expect(second.locator('.dashboard-container')).toBeVisible()
      checks.push(name + ': 确认重放拒绝、SSO Cookie刷新、并发标签恢复及真实SSE')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      expect(errors).toEqual([])
      await page.getByRole('button', { name: '用户菜单', exact: true }).click()
      await page.getByRole('menuitem', { name: '退出登录' }).click()
      await expect(page).toHaveURL(origin + '/login'); await expect(second).toHaveURL(origin + '/login')
      expect((await context.cookies()).some(item => item.name === '__Host-admincore_refresh')).toBe(false)
      expect((await context.request.get(origin + '/api/v1/auth/me/', { headers: { Authorization: 'Bearer ' + result.access } })).status()).toBe(401)
      await page.goto(callbackUrl)
      await expect(page).toHaveURL(origin + '/enterprise-login?result=failed')
      await expect(page.getByRole('alert')).toContainText('企业身份授权未完成')
      expect((await context.cookies()).some(item => item.name === '__Host-admincore_refresh')).toBe(false)
      await page.goto('/'); await expect(page).toHaveURL(origin + '/login'); await noPersistence(page)
      checks.push(name + ': 真实退出撤销、跨标签退出、回调重放拒绝且刷新不复活')
      await second.close()
      await context.tracing.stop()
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, 'sso-session-' + name + '-failure.png'), fullPage: true })
      await context.tracing.stop({ path: resolve(evidence, 'sso-session-' + name + '-failure.zip') })
      throw error
    } finally { await context.close() }
  }
  const probe = await browser.newContext({ ignoreHTTPSErrors: true })
  const summary = await (await probe.request.get(issuer + '/summary')).json()
  const factor = selected === 'desktop' ? 1 : 2
  expect(summary).toMatchObject({ authorized: 2 * factor, cancelled: factor, exchanged: 2 * factor })
  expect(summary.jwks).toBeGreaterThanOrEqual(2 * factor)
  await probe.close()
  writeFileSync(resolve(evidence, 'sso-browser-' + selected + '-report.json'), JSON.stringify({ passed: true, checks, provider: summary }, null, 2))
} finally { await browser.close() }
