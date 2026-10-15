import { test, expect, type Page } from '@playwright/test'

const env = (data: unknown) => ({ code: 200, message: 'success', data })
const paged = (items: unknown[]) => ({ items, pagination: { total: items.length, page: 1, page_size: 20, total_pages: 1 } })
async function setup(page: Page, admin = true) {
  const state = { admin, readStatus: 200, saveStatus: 200, writes: 0, sends: 0, keys: [] as string[], sendStatus: 503,
    row: { id: 'template-1', code: 'fixture', name: '通知夹具', enabled: true, revision: 1, current: { id: 'v1', number: 1, subject: 'Hello ${name}', body: 'Text ${name}', variables: ['name'], created_at: '2026-10-15T00:00:00Z' } } }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-message-fixture'))
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: env({ id: 'a1', username: 'fixture', is_staff: state.admin, permissions: state.admin ? ['*'] : [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: env({ name: 'AdminCore', tagline: 'fixture' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: env({ contract_version: 1, preset: 'standard', modules: [{ key: 'notifications', enabled: true, paths: ['/notifications'], dependencies: [] }] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: env([]) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: env({ count: 0 }) })
    if (path.endsWith('/templates/channels/')) return route.fulfill({ json: env([{ key: 'inapp', enabled: true }, { key: 'email', enabled: false }]) })
    if (path.endsWith('/templates/recipient-departments/')) return route.fulfill({ json: env({ enabled: false, items: [], truncated: false }) })
    if (path.endsWith('/templates/recipients/')) return route.fulfill({ json: env(paged([{ id: 'recipient-1', username: 'recipient', display_name: '收件夹具', department: null, department_name: null }])) })
    if (path.endsWith('/preview/')) return route.fulfill({ json: env({ subject: `Hello ${req.postDataJSON().values.name}`, body: req.postDataJSON().values.name }) })
    if (path.endsWith('/send/')) { state.sends++; state.keys.push(req.headers()['idempotency-key'] || ''); return route.fulfill({ status: state.sendStatus, json: state.sendStatus === 202 ? env({ count: 1 }) : { code: 503, message: 'fixture unavailable', data: null } }) }
    if (path.endsWith('/versions/')) return route.fulfill({ json: env(paged([{ ...state.row.current, body: '<img src=x onerror=window.messageInjected=1>' }])) })
    if (path.endsWith('/templates/')) return route.fulfill({ status: state.readStatus, json: state.readStatus === 200 ? env(paged([state.row])) : { code: 503, message: 'fixture read failed', data: null } })
    if (path.endsWith('/templates/template-1/') && req.method() === 'GET') return route.fulfill({ json: env(state.row) })
    if (path.endsWith('/templates/template-1/') && req.method() === 'PATCH') {
      state.writes++
      if (state.saveStatus !== 200) return route.fulfill({ status: state.saveStatus, json: { code: state.saveStatus, message: 'fixture conflict', data: null } })
      const data = req.postDataJSON(); Object.assign(state.row, { name: data.name, enabled: data.enabled, revision: state.row.revision + 1 }); Object.assign(state.row.current, data)
      return route.fulfill({ json: env(state.row) })
    }
    if (path.endsWith('/deliveries/')) return route.fulfill({ json: env(paged([{ id: 'd1', template_code: 'fixture', version_number: 1, recipient: 'recipient-1', channel: 'inapp', status: 'succeeded', attempts: 1, last_error: '', request_id: 'request-fixture', expires_at: '2099-01-01' }])) })
    return route.fulfill({ json: env(paged([])) })
  })
  return state
}

test('模板历史安全文本、手机深色布局、Esc 返回焦点', async ({ page }, info) => {
  await setup(page); await page.addInitScript(() => localStorage.setItem('theme', 'dark')); await page.goto('/notifications/templates')
  const trigger = page.getByRole('button', { name: '版本记录', exact: true }); await trigger.click()
  const dialog = page.getByRole('dialog', { name: '版本记录', exact: true })
  await expect(dialog).toContainText('<img src=x onerror=window.messageInjected=1>'); await expect(dialog.locator('img')).toHaveCount(0)
  expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).messageInjected)).toBeUndefined()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.screenshot({ path: info.outputPath('message-versions-dark.png'), fullPage: true })
  await page.keyboard.press('Escape'); await expect(dialog).not.toBeVisible(); await expect(trigger).toBeFocused()
})

test('版本冲突保留输入、取消编辑需确认、成功保存新版本', async ({ page }) => {
  const state = await setup(page); await page.goto('/notifications/templates'); await page.getByRole('button', { name: '编辑', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '编辑模板', exact: true })
  await dialog.getByLabel('模板名称', { exact: true }).fill('private template draft')
  state.saveStatus = 409; await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog.getByRole('region', { name: '编辑冲突' })).toBeVisible(); await expect(dialog.getByLabel('模板名称', { exact: true })).toHaveValue('private template draft')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  const prompt = page.getByRole('dialog').filter({ hasText: '尚有未保存的修改，确定放弃吗？' }); await prompt.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog).toBeVisible(); state.saveStatus = 200; await dialog.getByRole('button', { name: '查看服务器最新值', exact: true }).click(); await dialog.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click(); await dialog.getByLabel('模板名称', { exact: true }).fill('reviewed draft'); await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog).not.toBeVisible(); expect(state.writes).toBe(2)
  expect(await page.evaluate(() => Object.values(localStorage).some(value => value.includes('private template draft')))).toBe(false)
})

test('邮件禁用、变量修改使预览失效、取消无发送、重试保留幂等键', async ({ page }) => {
  const state = await setup(page); await page.goto('/notifications/templates'); await page.getByRole('button', { name: '发送通知', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '发送通知', exact: true })
  await expect(dialog.getByRole('checkbox', { name: 'SMTP 邮件' })).toBeDisabled()
  await dialog.getByLabel('name', { exact: true }).fill('<img src=x onerror=window.messageInjected=1>')
  await dialog.getByRole('button', { name: '预览通知', exact: true }).click(); await expect(dialog.getByRole('region', { name: '通知预览' })).toContainText('<img src=x')
  await expect(dialog.locator('img')).toHaveCount(0)
  await dialog.getByLabel('name', { exact: true }).fill('changed'); await expect(dialog.getByRole('region', { name: '通知预览' })).toHaveCount(0)
  await dialog.getByRole('button', { name: '选择人员', exact: true }).click()
  const picker = page.getByRole('dialog', { name: '选择人员', exact: true }); await picker.getByRole('radio').first().focus(); await page.keyboard.press('Space'); await expect(picker.getByRole('radio').first()).toBeChecked(); await picker.getByRole('button', { name: '确认', exact: true }).click()
  await dialog.getByRole('button', { name: '添加收件人', exact: true }).click(); await dialog.getByRole('button', { name: '预览通知', exact: true }).click()
  await dialog.getByRole('button', { name: '确认发送', exact: true }).click()
  const prompt = page.getByRole('dialog').filter({ hasText: '确定向所选人员登记通知投递吗？' }); await prompt.getByRole('button', { name: '取消', exact: true }).click(); expect(state.sends).toBe(0)
  await dialog.getByRole('button', { name: '确认发送', exact: true }).click(); await prompt.getByRole('button', { name: '确定', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('发送未确认，已保留输入'); state.sendStatus = 202
  await dialog.getByRole('button', { name: '确认发送', exact: true }).click(); await prompt.getByRole('button', { name: '确定', exact: true }).click()
  await expect(dialog).not.toBeVisible(); expect(state.sends).toBe(2); expect(state.keys[0]).toBeTruthy(); expect(state.keys[0]).toBe(state.keys[1])
  await expect(page.getByRole('cell', { name: 'request-fixture', exact: true })).toBeAttached()
})

test('英文加载失败可重试，普通用户直接路由被拒绝', async ({ page }) => {
  const state = await setup(page); state.readStatus = 503; await page.addInitScript(() => localStorage.setItem('language', 'en-US')); await page.goto('/notifications/templates')
  await expect(page.getByRole('heading', { name: 'Notification Templates', exact: true })).toBeVisible()
  await expect(page.locator('.el-alert')).toContainText('Could not load notification settings'); state.readStatus = 200
  await page.getByRole('button', { name: 'Refresh', exact: true }).click(); await expect(page.getByRole('cell', { name: '通知夹具', exact: true })).toBeVisible()
  state.admin = false; await page.reload(); await expect(page).toHaveURL(/\/403$/); expect(state.writes + state.sends).toBe(0)
})
