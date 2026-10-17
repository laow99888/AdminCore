/** 真实产品构建 + Django/SQL/HTTPS；不持久化成功测试中的凭据或令牌。 */
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createHmac } from 'node:crypto'
const [frontend, evidence, port] = process.argv.slice(2)
const { chromium, devices, expect } = createRequire(resolve(frontend, 'package.json'))('@playwright/test')
const { password } = JSON.parse(readFileSync(resolve(evidence, 'browser-access.json'), 'utf8'))
const origin = `https://127.0.0.1:${port}`
const browser = await chromium.launch({ headless: true })
const checks = []
const sid = access => JSON.parse(Buffer.from(access.split('.')[1], 'base64url').toString('utf8')).sid
// RFC 6238 SHA-1 / 30 秒 / 6 位；密钥只在本次隔离测试内存中使用。
function totp(secret) {
  const bits = [...secret].map(letter => 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'.indexOf(letter).toString(2).padStart(5, '0')).join('')
  const key = Buffer.from(bits.match(/.{8}/g).map(byte => parseInt(byte, 2)))
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)))
  const digest = createHmac('sha1', key).update(counter).digest(), offset = digest.at(-1) & 15
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1000000).toString().padStart(6, '0')
}
async function login(page, username) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill(username)
  await page.getByPlaceholder('密码', { exact: true }).fill(password)
  const response = page.waitForResponse(res => res.url().endsWith('/auth/login/') && res.request().method() === 'POST')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const body = await (await response).json()
  expect(body.refresh).toBeUndefined(); expect(body.session_transport).toBe('cookie')
  await expect(page).toHaveURL(origin + '/')
  await expect(page.locator('.dashboard-container')).toBeVisible()
  return body.access
}
async function noPersistence(page) {
  expect(await page.evaluate(() => [localStorage.getItem('token'), localStorage.getItem('refreshToken'),
    sessionStorage.getItem('token'), sessionStorage.getItem('refreshToken')])).toEqual([null, null, null, null])
  expect(await page.evaluate(() => document.cookie)).not.toContain('admincore_refresh')
}
try {
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    // 每个设备使用独立身份，避免两套安全管理流程合计越过每身份 5 次/分钟的真实限流。
    const username = name === 'desktop' ? 'admin' : 'mobile-admin'
    const context = await browser.newContext({ ...device, baseURL: origin, ignoreHTTPSErrors: true })
    await context.addInitScript(() => {
      window.__fixtureSnapshots = 0
      window.addEventListener('admincore:realtime-snapshot', () => { window.__fixtureSnapshots++ })
    })
    await context.tracing.start({ screenshots: true, snapshots: true })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    try {
      const streams = []
      // 只观察并放行真实请求；在发送前读取完整头，避免长连接结束前 allHeaders 等待。
      await page.route('**/api/v1/realtime/events/', async route => {
        const request = route.request()
        try {
          const headers = await request.allHeaders()
          streams.push({
            sameOrigin: new URL(request.url()).origin === origin, search: new URL(request.url()).search,
            bearer: /^Bearer /.test(headers.authorization ?? ''), cookie: !!headers.cookie,
            session: sid(headers.authorization.replace(/^Bearer /, '')),
          })
        } catch { /* 已取消的请求不参与成功请求断言。 */ }
        finally { await route.continue().catch(() => {}) }
      })
      const original = await login(page, username)
      await expect.poll(() => page.evaluate(() => window.__fixtureSnapshots)).toBeGreaterThan(0)
      await noPersistence(page)
      const cookie = (await context.cookies()).find(item => item.name === '__Host-admincore_refresh')
      expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: 'Lax', path: '/' })
      checks.push(name + ': HTTPS登录、Host HttpOnly Cookie、无Web Storage凭据')
      // 真服务器拒绝缺失CSRF、错误Origin；APIRequestContext不自动带浏览器Origin。
      expect((await context.request.post(origin + '/api/v1/auth/browser-session/', { data: {} })).status()).toBe(403)
      const proof = (await (await context.request.get(origin + '/api/v1/auth/browser-session/')).json()).data.csrf_token
      expect((await context.request.post(origin + '/api/v1/auth/browser-session/', {
        headers: { Origin: 'https://evil.example', 'X-CSRFToken': proof }, data: {} })).status()).toBe(403)
      expect((await context.request.get(origin + '/api/v1/auth/me/')).status()).toBe(401)
      checks.push(name + ': 实际CSRF/Origin拒绝、Cookie不能独立鉴权业务')
      await page.reload(); await expect(page.locator('.dashboard-container')).toBeVisible(); await noPersistence(page)
      const second = await context.newPage()
      await second.goto('/'); await expect(second.locator('.dashboard-container')).toBeVisible()
      await Promise.all([page.reload(), second.reload()])
      await expect(page).toHaveURL(origin + '/'); await expect(second).toHaveURL(origin + '/')
      await expect(page.locator('.dashboard-container')).toBeVisible()
      await expect(second.locator('.dashboard-container')).toBeVisible()
      await noPersistence(second)
      checks.push(name + ': 刷新恢复和两个标签并发恢复')
      // 仅注入一次过期access响应，其后的刷新、me与业务请求均走真实后端。
      let expired = false
      await page.route('**/api/v1/auth/me/', async route => {
        if (!expired) { expired = true; return route.fulfill({ status: 401, json: { code: 401, message: 'expired', data: null } }) }
        return route.continue()
      })
      await page.goto('/settings/sessions')
      await expect(page.getByRole('heading', { name: '会话与设备' })).toBeVisible()
      await expect.poll(() => streams.length).toBeGreaterThan(0)
      expect(streams.every(stream => stream.sameOrigin && !stream.search && stream.bearer && !stream.cookie)).toBe(true)
      expect(expired).toBe(true)
      await page.unroute('**/api/v1/auth/me/')
      checks.push(name + ': 401后真实Cookie刷新并恢复设备页')
      // 退出从可观察的产品菜单发起，另一标签通过无凭据marker清空并重载。
      await page.getByRole('button', { name: '用户菜单', exact: true }).click()
      await page.getByRole('menuitem', { name: '退出登录' }).click()
      await expect(page).toHaveURL(origin + '/login')
      await expect(second).toHaveURL(origin + '/login')
      expect((await context.cookies()).some(item => item.name === '__Host-admincore_refresh')).toBe(false)
      expect((await context.request.get(origin + '/api/v1/auth/me/', { headers: { Authorization: 'Bearer ' + original } })).status()).toBe(401)
      await page.reload(); await expect(page).toHaveURL(origin + '/login')
      await noPersistence(page)
      expect(await page.evaluate(() => window.__fixtureSnapshots)).toBe(0)
      checks.push(name + ': 真实退出撤销、跨标签退出及刷新不复活')
      const beforeTotp = await login(page, username); await expect(second.locator('.dashboard-container')).toBeVisible()
      await expect(page.getByRole('button', { name: '用户菜单', exact: true })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      expect(errors).toEqual([])
      await page.screenshot({ path: resolve(evidence, 'browser-session-' + name + '.png'), fullPage: true })
      checks.push(name + ': 跨标签新登录恢复、布局和无页面异常')
      // 服务端同一设备只允许一条 SSE，其它标签按既有策略轮询；安全替换阶段留一个标签。
      await second.close(); await page.bringToFront()
      await page.goto('/settings/two-factor')
      await page.getByRole('textbox', { name: '当前密码', exact: true }).fill(password)
      const setupResponse = page.waitForResponse(res => res.url().endsWith('/auth/totp/setup/'))
      await page.getByRole('button', { name: '生成认证器密钥', exact: true }).click()
      const seed = (await (await setupResponse).json()).data.secret
      const enableResponse = page.waitForResponse(res => res.url().endsWith('/auth/totp/enable/'))
      const beforeEnable = await page.evaluate(() => window.__fixtureSnapshots)
      await page.getByRole('textbox', { name: '当前密码', exact: true }).fill(password)
      await page.getByRole('textbox', { name: '认证器动态码', exact: true }).fill(totp(seed))
      await page.getByRole('button', { name: '确认启用双因素认证', exact: true }).click()
      const replacement = (await (await enableResponse).json()).data
      expect(replacement.refresh).toBeUndefined(); expect(replacement.session_transport).toBe('cookie')
      await expect(page.getByRole('heading', { name: '保存一次性恢复码', exact: true })).toBeVisible()
      await expect.poll(() => streams.some(stream => stream.session === sid(replacement.access))).toBe(true)
      await expect.poll(() => page.evaluate(() => window.__fixtureSnapshots)).toBeGreaterThan(beforeEnable)
      await noPersistence(page)
      expect((await context.request.get(origin + '/api/v1/auth/me/', { headers: { Authorization: 'Bearer ' + beforeTotp } })).status()).toBe(401)
      await page.getByText('我已保存恢复码', { exact: true }).click()
      await page.getByRole('button', { name: '完成并清除恢复码', exact: true }).click()
      // 错误恢复码实际得到 401；它不应被当作 access 过期，导致持锁刷新或清空登录态。
      await page.getByRole('textbox', { name: '当前密码', exact: true }).fill(password)
      await page.getByRole('textbox', { name: '动态码或恢复码', exact: true }).fill('0'.repeat(32))
      await page.getByRole('button', { name: '停用双因素认证', exact: true }).click()
      const badProof = page.waitForResponse(res => res.url().endsWith('/auth/totp/disable/'))
      await page.getByRole('button', { name: '确定', exact: true }).click()
      expect((await badProof).status()).toBe(401)
      await expect(page.getByRole('alert').filter({ hasText: '安全修改未确认' })).toBeVisible()
      await expect(page).toHaveURL(origin + '/settings/two-factor')
      await page.getByRole('textbox', { name: '当前密码', exact: true }).fill(password)
      await page.getByRole('textbox', { name: '动态码或恢复码', exact: true }).fill(replacement.recovery_codes[0])
      await page.getByRole('button', { name: '停用双因素认证', exact: true }).click()
      const disableResponse = page.waitForResponse(res => res.url().endsWith('/auth/totp/disable/'))
      const beforeDisable = await page.evaluate(() => window.__fixtureSnapshots)
      await page.getByRole('button', { name: '确定', exact: true }).click()
      const disabled = await disableResponse
      expect(disabled.status()).toBe(200)
      const disabledSession = (await disabled.json()).data
      await expect(page.getByText('双因素认证已停用；全部旧会话已撤销。', { exact: true })).toBeVisible()
      await expect.poll(() => streams.some(stream => stream.session === sid(disabledSession.access))).toBe(true)
      await expect.poll(() => page.evaluate(() => window.__fixtureSnapshots)).toBeGreaterThan(beforeDisable)
      await page.reload()
      await expect(page.getByText('未启用', { exact: true })).toBeVisible()
      await noPersistence(page)
      checks.push(name + ': 实际TOTP启用与停用、会话替换、错误证明401不退出、刷新恢复')
      checks.push(name + ': 真实HTTPS ASGI快照、内存Bearer且无Cookie/URL令牌、退出停止并在会话替换后恢复')
      await context.tracing.stop()
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, 'browser-session-' + name + '-failure.png'), fullPage: true })
      await context.tracing.stop({ path: resolve(evidence, 'browser-session-' + name + '-failure.zip') })
      throw error
    } finally { await context.close() }
  }
  writeFileSync(resolve(evidence, 'browser-report.json'), JSON.stringify({ passed: true, checks }, null, 2))
} finally { await browser.close() }
