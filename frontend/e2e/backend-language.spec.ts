import { expect, test } from '@playwright/test'

for (const [language, header, username, password, button, message] of [
  ['en-US', 'en', 'Username', 'Password', 'Sign In', 'The request contains unsupported fields.'],
  ['zh-CN', 'zh-Hans', '用户名', '密码', '登录', '请求包含不允许的字段'],
]) {
  test(`后端错误提示使用当前语言 ${language}，不重复提示或清除输入`, async ({ page }, info) => {
    await page.addInitScript(language => { localStorage.clear(); localStorage.setItem('language', language!) }, language)
    let seen = ''
    await page.route('**/api/v1/**', route => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/auth/login/')) {
        seen = route.request().headers()['accept-language'] || ''
        return route.fulfill({ status: 400, headers: { 'Content-Language': header! }, json: { code: 400, message, data: null } })
      }
      return route.fulfill({ json: { code: 200, message: 'success', data: path.endsWith('/brand/') ? { name: 'AdminCore' } : { enabled: false } } })
    })
    await page.goto('/login')
    await page.getByPlaceholder(username!, { exact: true }).fill('isolated-member')
    await page.getByPlaceholder(password!, { exact: true }).fill('isolated-not-a-real-password')
    await page.getByRole('button', { name: button!, exact: true }).click()
    await expect(page.getByText(message!, { exact: true })).toHaveCount(1)
    expect(seen).toBe(header)
    await expect(page.getByPlaceholder(username!, { exact: true })).toHaveValue('isolated-member')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath('backend-error-language.png'), fullPage: true })
  })
}
