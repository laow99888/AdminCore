import { expect, test } from '@playwright/test'

test('登录等待响应期间重复回车只发送一次请求，失败后可重试', async ({ page }) => {
  await page.addInitScript(() => localStorage.clear())
  let requests = 0
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/login/')) {
      requests++
      await pending
      return route.fulfill({ status: 401, json: { code: 401, message: 'Invalid isolated fixture', data: null } })
    }
    return route.fulfill({ json: { code: 200, message: 'success', data: { name: 'AdminCore' } } })
  })
  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('isolated-login-fixture')
  await page.getByPlaceholder('密码', { exact: true }).fill('isolated-request-fixture')
  const requested = page.waitForRequest(request => new URL(request.url()).pathname.endsWith('/auth/login/'))
  await page.locator('.login-form').dispatchEvent('keyup', { key: 'Enter' })
  await requested
  await page.locator('.login-form').dispatchEvent('keyup', { key: 'Enter' })
  await page.locator('.login-form').dispatchEvent('submit')
  await expect(page.getByPlaceholder('用户名', { exact: true })).toBeDisabled()
  await expect(page.getByPlaceholder('密码', { exact: true })).toBeDisabled()
  expect(requests).toBe(1)
  release()
  await expect(page.getByRole('button', { name: '登录', exact: true })).toBeEnabled()
  await expect(page.getByPlaceholder('用户名', { exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect.poll(() => requests).toBe(2)
  await expect(page).toHaveURL(/\/login$/)
})
