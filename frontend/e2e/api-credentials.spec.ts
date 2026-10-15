import { expect, test, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const secret = 'one-time-browser-fixture-secret'
async function setup(page: Page) {
  const state = { enabled: true, permissions: ['*'], fail: false, creates: [] as Record<string, unknown>[], revokes: [] as Record<string, unknown>[], revoked: false }
  await page.addInitScript(() => { localStorage.setItem('token', 'isolated-api-manager'); localStorage.setItem('refreshToken', 'isolated-api-refresh') })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'owner', username: 'owner', permissions: state.permissions }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'api_credentials', title: '只读开放 API', enabled: state.enabled, dependencies: [], paths: ['/integrations/credentials'], page_permissions: { '/integrations/credentials': 'api_credential:read' } }] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/credentials/scopes/')) return route.fulfill({ json: envelope([{ code: 'task:read', label: '读取任务摘要' }]) })
    if (path.endsWith('/credentials/') && route.request().method() === 'POST') {
      state.creates.push(route.request().postDataJSON())
      return route.fulfill({ status: state.fail ? 400 : 201, json: envelope({ id: 'credential-fixture', token: secret }) })
    }
    if (path.endsWith('/credentials/')) return route.fulfill({ json: envelope({ items: [{ id: 'credential-fixture', name: 'Existing credential', scopes: ['task:read'], created_at: '2026-10-16T00:00:00Z', expires_at: '2026-10-20T00:00:00Z', revoked_at: state.revoked ? '2026-10-16T01:00:00Z' : null, last_used_at: null }], pagination: { total: 1, page: 1, page_size: 10, total_pages: 1 } }) })
    if (path.endsWith('/revoke/')) {
      state.revokes.push(route.request().postDataJSON()); state.revoked = true
      return route.fulfill({ json: envelope(null) })
    }
    return route.fulfill({ json: envelope({}) })
  })
  return state
}

test('创建本人只读凭证必须密码确认；密钥只在临时窗口展示且不写浏览器存储', async ({ page }, info) => {
  const state = await setup(page)
  await page.goto('/integrations/credentials')
  await expect(page.getByRole('heading', { name: '开放凭证', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '名称', exact: true }).fill('Browser integration')
  await page.getByText('读取任务摘要', { exact: true }).click()
  await page.getByRole('button', { name: '确认创建', exact: true }).click()
  const confirmation = page.getByRole('dialog')
  await expect(confirmation.getByRole('button', { name: '确认', exact: true })).toBeDisabled()
  await confirmation.getByRole('textbox', { name: '当前密码' }).fill('isolated-confirmation')
  await confirmation.getByRole('button', { name: '确认', exact: true }).click()
  const issued = page.getByRole('dialog', { name: '密钥仅展示一次', exact: true })
  await expect(issued.getByRole('textbox', { name: '开放 API 密钥' })).toHaveValue(secret)
  expect(state.creates).toHaveLength(1)
  expect(state.creates[0]).toMatchObject({ name: 'Browser integration', scopes: ['task:read'], current_password: 'isolated-confirmation' })
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain(secret)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('api-credentials.png'), fullPage: true })
  await issued.getByRole('button', { name: '已保存，关闭' }).click()
  await expect(page.locator('#issued-api-secret')).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: '开放凭证', exact: true })).toBeVisible()
  await expect(page.locator('#issued-api-secret')).toHaveCount(0)
})

test('签发失败清密码可重试；撤销只针对所选本人凭证并需要再次确认', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/integrations/credentials')
  await page.getByRole('textbox', { name: '名称', exact: true }).fill('Retry fixture')
  await page.getByText('读取任务摘要', { exact: true }).click()
  await page.getByRole('button', { name: '确认创建', exact: true }).click()
  const dialog = page.getByRole('dialog')
  state.fail = true
  await dialog.getByRole('textbox', { name: '当前密码' }).fill('wrong-fixture')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('操作未确认')
  await expect(dialog.getByRole('textbox', { name: '当前密码' })).toHaveValue('')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('row').filter({ hasText: 'Existing credential' }).getByRole('button', { name: '撤销凭证' }).click()
  await dialog.getByRole('textbox', { name: '当前密码' }).fill('revoke-fixture')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(state.revokes).toEqual([{ current_password: 'revoke-fixture' }])
  await expect(page.getByRole('row').filter({ hasText: 'Existing credential' }).getByRole('button', { name: '撤销凭证' })).toBeDisabled()
})

test('只有读取权限不显示创建与撤销；模块关闭拒绝页面', async ({ page }) => {
  const state = await setup(page)
  state.permissions = ['api_credential:read']
  await page.goto('/integrations/credentials')
  await expect(page.getByRole('heading', { name: '开放凭证', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '确认创建' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '撤销凭证' })).toHaveCount(0)
  state.enabled = false
  await page.reload()
  await expect(page).toHaveURL('http://127.0.0.1:18411/')
  await expect(page.getByRole('heading', { name: '开放凭证', exact: true })).toHaveCount(0)
})
