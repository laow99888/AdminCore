import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
async function setup(page: Page, mode: 'write' | 'read' | 'off' = 'write') {
  const state = { mode, fail: false, conflict: false, empty: false, reads: 0, saves: [] as { method: string; data: Record<string, unknown>; key?: string }[], deletes: 0 }
  const flag = { id: 'flag1', key: 'orders.review', name: '订单复核', description: '逐步启用复核功能', enabled: true, rollout: 2500, included_users: [], excluded_users: [], roles: [], version: 1 }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-flags-fixture'))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'owner', username: 'owner', permissions: state.mode === 'write' ? ['feature_flag:read', 'feature_flag:create', 'feature_flag:update', 'feature_flag:delete'] : ['feature_flag:read'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'feature_flags', title: '特性开关', enabled: state.mode !== 'off', dependencies: [], paths: ['/system/feature-flags'], page_permissions: { '/system/feature-flags': 'feature_flag:read' } }] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'menu', name: '特性开关', path: '/system/feature-flags', icon: 'settings', children: [] }]) })
    if (path.endsWith('/feature-flags/targets/')) return route.fulfill({ json: envelope([]) })
    if (path.includes('/feature-flags/flags/')) {
      if (method === 'DELETE') { state.deletes++; return route.fulfill({ json: envelope(null) }) }
      if (method === 'POST' || method === 'PATCH') {
        state.saves.push({ method, data: route.request().postDataJSON(), key: route.request().headers()['idempotency-key'] })
        if (state.conflict) return route.fulfill({ status: 409, json: { code: 409, message: '记录已变化', data: null } })
        return route.fulfill({ status: method === 'POST' ? 201 : 200, json: envelope(flag) })
      }
      state.reads++
      if (state.fail) return route.fulfill({ status: 503, json: { code: 503, message: 'fixture unavailable', data: null } })
      return route.fulfill({ json: envelope(path.endsWith('/flag1/') ? { ...flag, version: 2, name: '服务器新名称' } : { items: state.empty ? [] : [flag], pagination: { total: state.empty ? 0 : 1, page: 1, page_size: 10, total_pages: 1 } }) })
    }
    return route.fulfill({ json: envelope({}) })
  })
  return state
}

test('只读列表展示灰度且手机无页面溢出', async ({ page }, info) => {
  await setup(page, 'read'); await page.goto('/system/feature-flags')
  await expect(page.getByText('orders.review', { exact: true })).toBeVisible()
  await expect(page.getByText('25%', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '新增开关', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('flags-read.png'), fullPage: true, animations: 'disabled' })
})

test('创建默认关闭并带初始版本和幂等键，重复点击不重发', async ({ page }, info) => {
  const state = await setup(page); await page.goto('/system/feature-flags')
  await page.getByRole('button', { name: '新增开关', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: '开关标识', exact: true }).fill('billing.preview')
  await dialog.getByRole('textbox', { name: '名称', exact: true }).fill('账单预览')
  await expect(dialog.getByRole('switch', { name: '启用开关', exact: true })).not.toBeChecked()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('flags-form.png'), fullPage: true, animations: 'disabled' })
  await dialog.getByRole('button', { name: '保存', exact: true }).dblclick()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0].method).toBe('POST')
  expect(state.saves[0].key).toMatch(/^feature-flag-/)
  expect(state.saves[0].data).toEqual({ key: 'billing.preview', name: '账单预览', description: '', enabled: false, rollout: 0, included_users: [], excluded_users: [], roles: [], version: 0 })
})

test('编辑冲突保留草稿，显式载入后使用服务器版本保存', async ({ page }) => {
  const state = await setup(page); state.conflict = true; await page.goto('/system/feature-flags')
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  const dialog = page.getByRole('dialog'), name = dialog.getByRole('textbox', { name: '名称', exact: true })
  await expect(dialog.getByRole('textbox', { name: '开关标识', exact: true })).toBeDisabled()
  await name.fill('保留我的草稿'); await dialog.getByRole('button', { name: '保存', exact: true }).click()
  const panel = dialog.getByRole('region', { name: '编辑冲突' })
  await expect(panel).toBeVisible(); await expect(name).toHaveValue('保留我的草稿')
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.getByRole('table')).toContainText('服务器新名称'); await expect(name).toHaveValue('保留我的草稿')
  await panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click()
  await expect(name).toHaveValue('服务器新名称'); state.conflict = false
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect.poll(() => state.saves.length).toBe(2)
  expect(state.saves[1].data.version).toBe(2)
})

test('空状态和错误可恢复，模块关闭不请求规则', async ({ page }) => {
  const state = await setup(page, 'off'); await page.goto('/system/feature-flags')
  await expect(page).toHaveURL('/'); expect(state.reads).toBe(0)
  state.mode = 'read'; state.empty = true; await page.reload(); await page.goto('/system/feature-flags')
  await expect(page.getByText('暂无数据', { exact: true })).toBeVisible()
  state.fail = true; await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '加载失败，请重试' })).toBeVisible()
  state.fail = false; state.empty = false; await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByText('orders.review', { exact: true })).toBeVisible()
})
