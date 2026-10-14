import { test, expect } from '@playwright/test'

test('真实接口形状的精简login和完整me不会中断登录导航', async ({ page }) => {
  const user = { id: 'contract-user', username: 'admin', email: '', first_name: '', last_name: '', must_change_password: false }
  const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
  await page.addInitScript(() => localStorage.clear())
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/login/')) return route.fulfill({ json: { access: 'isolated-contract-access', refresh: 'isolated-contract-refresh', user } })
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ ...user, permissions: ['*'], is_superuser: true, is_staff: true, has_avatar: false }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/auth/recovery/config/')) return route.fulfill({ json: envelope({ enabled: false }) })
    return route.fulfill({ json: envelope({ totals: {}, login_trend: [], task_status: {}, items: [], count: 0 }) })
  })
  await page.goto('/login')
  await page.getByPlaceholder('用户名', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill('fixture-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByPlaceholder('密码', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBe('isolated-contract-access')
})
