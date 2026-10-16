import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })

async function setup(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'tenant-browser-fixture')
    localStorage.setItem('locale', 'zh-CN')
  })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/modules/')) {
      return route.fulfill({ json: envelope({
        contract_version: 1,
        preset: 'standard',
        modules: [
          { key: 'organization', enabled: true, paths: ['/organization'], dependencies: [] },
          { key: 'notifications', enabled: true, paths: ['/notifications'], dependencies: [] },
          { key: 'realtime', enabled: false, paths: [], dependencies: [] },
        ],
      }) })
    }
    if (path.endsWith('/auth/me/')) {
      return route.fulfill({ json: envelope({
        id: 'tenant-user', username: 'tenant-user', is_staff: false, is_superuser: false,
        permissions: ['task:read'], must_change_password: false,
      }) })
    }
    if (path.endsWith('/organization/my-tenants/')) {
      return route.fulfill({ json: envelope([
        { id: 'tenant-a', slug: 'tenant-a', name: '租户 A', role: 'member' },
        { id: 'tenant-b', slug: 'tenant-b', name: '租户 B', role: 'member' },
      ]) })
    }
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (path.endsWith('/dashboard/stats/')) {
      return route.fulfill({ json: envelope({ totals: {}, login_trend: [], task_status: {} }) })
    }
    return route.fulfill({ json: envelope({}) })
  })
}

test('多租户选择器切换后刷新并携带租户请求头', async ({ page }) => {
  await setup(page)
  await page.goto('/')
  const selector = page.getByRole('combobox', { name: '当前租户' })
  await expect(selector).toBeVisible()
  await page.locator('.tenant-switcher .el-select').click()
  const refreshed = page.waitForRequest(request => request.url().endsWith('/api/v1/dashboard/stats/'))
  await page.getByRole('option', { name: '租户 B', exact: true }).click()

  const dashboardRequest = await refreshed
  expect(await page.evaluate(() => localStorage.getItem('admincore.tenant'))).toBe('tenant-b')
  expect(dashboardRequest.headers()['x-admincore-tenant']).toBe('tenant-b')
})
