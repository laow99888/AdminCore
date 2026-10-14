import { test, expect, type Page } from '@playwright/test'
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })

async function setup(page: Page, mode: 'write' | 'read' | 'off' = 'write') {
  const state = { mode, saves: [] as any[], deletes: 0, fail: false, detailFail: false, getCount: 0 }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-example-fixture'))
  const item = { id: 'item1', title: '复用基座的真实业务契约', notes: '<script>literal content</script>\n说明原文', status: 'open', priority: 'high', creator: 'owner', creator_name: 'owner', version: 1 }
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method()
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'owner', username: 'owner', permissions: state.mode === 'write' ? ['example:read', 'example:create', 'example:update', 'example:delete'] : ['example:read'] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [{ key: 'example', title: 'sample', enabled: state.mode !== 'off', dependencies: [], paths: ['/example'], page_permissions: { '/example': 'example:read' } }] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'menu', name: '示例工单', path: '/example', icon: 'clipboard-check', children: [] }]) })
    if (path.includes('/example/items/')) {
      if (method === 'DELETE') { state.deletes++; return route.fulfill({ json: envelope(null) }) }
      if (method === 'PATCH' || method === 'POST') { state.saves.push({ method, data: route.request().postDataJSON(), key: route.request().headers()['idempotency-key'] }); if (state.fail) return route.fulfill({ status: 409, json: { code: 409, message: '记录已变化', data: null } }); return route.fulfill({ status: method === 'POST' ? 201 : 200, json: envelope(item) }) }
      state.getCount++
      if (path.endsWith('/item1/') && state.detailFail) return route.fulfill({ status: 503, json: { code: 503, message: 'fixture unavailable', data: null } })
      return route.fulfill({ json: envelope(path.endsWith('/item1/') ? item : { items: [item], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } }) })
    }
    return route.fulfill({ json: envelope({}) })
  })
  return state
}

test('只读查看转义正文，窄屏无页面溢出', async ({ page }, info) => {
  const state = await setup(page, 'read'); await page.goto('/example')
  await expect(page.getByRole('button', { name: '新增工单', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '详情', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('<script>literal content</script>', { exact: false })).toBeVisible()
  expect(state.saves.length).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('example-read.png'), fullPage: true, animations: 'disabled' })
})

test('新建双击只有一次请求，提交版本和幂等键', async ({ page }) => {
  const state = await setup(page); await page.goto('/example')
  await page.getByRole('button', { name: '新增工单', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: '工单标题', exact: true }).fill('new title')
  await dialog.getByRole('button', { name: '保存', exact: true }).dblclick()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0].data).toEqual({ title: 'new title', notes: '', status: 'open', priority: 'normal', version: 0 })
  expect(state.saves[0].key).toMatch(/^example-/)
})

test('冲突保留输入，加载当前版本需先确认', async ({ page }, info) => {
  const state = await setup(page); state.fail = true; await page.goto('/example')
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: '工单标题', exact: true }).fill('unsaved title')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('输入已保留')
  await expect(dialog.getByRole('textbox', { name: '工单标题', exact: true })).toHaveValue('unsaved title')
  await page.screenshot({ path: info.outputPath('example-conflict.png'), fullPage: true, animations: 'disabled' })
  await dialog.getByRole('button', { name: '重新加载', exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(dialog.getByRole('textbox', { name: '工单标题', exact: true })).toHaveValue('复用基座的真实业务契约')
})

test('关闭模块没有页面请求，确认期间撤权不发送删除', async ({ page }) => {
  const state = await setup(page, 'off'); await page.goto('/example')
  await expect(page).toHaveURL('/')
  expect(state.getCount).toBe(0)
  state.mode = 'write'; await page.reload(); await page.goto('/example')
  await page.clock.install()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  state.mode = 'read'
  const refreshed = page.waitForResponse('**/auth/me/')
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await refreshed
  await expect(page.getByRole('button', { name: '删除', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '确定', exact: true }).click()
  expect(state.deletes).toBe(0)
})

test('冲突重新加载失败保留输入并允许再次恢复', async ({ page }) => {
  const state = await setup(page); state.fail = true; state.detailFail = true
  await page.goto('/example')
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('textbox', { name: '工单标题', exact: true }).fill('retained after read failure')
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('输入已保留')
  await dialog.getByRole('button', { name: '重新加载', exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('重新加载失败')
  await expect(dialog.getByRole('textbox', { name: '工单标题', exact: true })).toHaveValue('retained after read failure')
  state.detailFail = false
  await dialog.getByRole('button', { name: '重新加载', exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(dialog.getByRole('textbox', { name: '工单标题', exact: true })).toHaveValue('复用基座的真实业务契约')
})
