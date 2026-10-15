import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const paged = (items: unknown[]) => ({ items, pagination: { total: items.length, page: 1, page_size: 20, total_pages: 1 } })
const initial = () => ({ id: 'announcement-1', title: '公告标题', content: '<img src=x onerror=alert(1)>\n纯文本正文', status: 'draft', version: 1, published_at: null as string | null, created_at: '2026-10-14T00:00:00Z', updated_at: '2026-10-14T00:00:00Z' })
async function setup(page: Page, admin = true) {
  const state = { writes: 0, status: 200, readStatus: 200, delay: undefined as Promise<void> | undefined, row: initial(), admin, enabled: true }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-announcement-fixture'))
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'a1', username: state.admin ? 'admin' : 'member', is_staff: state.admin, permissions: state.admin ? ['*'] : [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: 'fixture' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: ['files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization'].map(key => ({ key, enabled: key !== 'notifications' || state.enabled, paths: key === 'system' ? ['/system/config'] : key === 'data_io' ? [] : [`/${key}`], dependencies: [] })) }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (path.includes('/announcements/')) {
      const manage = path.includes('/manage/')
      if (request.method() === 'GET') {
        if (state.readStatus !== 200) return route.fulfill({ status: state.readStatus, json: { code: state.readStatus, message: 'fixture read failed', data: null } })
        if (path.endsWith(`/${state.row.id}/`)) return route.fulfill({ json: envelope({ ...state.row }) })
        return route.fulfill({ json: envelope(paged(manage || state.row.status === 'published' ? [{ ...state.row }] : [])) })
      }
      state.writes++
      if (state.delay) await state.delay
      if (state.status !== 200) return route.fulfill({ status: state.status, json: { code: state.status, message: 'fixture conflict', data: null } })
      if (path.endsWith('/publish/')) { state.row.status = 'published'; state.row.version++; state.row.published_at = '2026-10-14T01:00:00Z' }
      else if (path.endsWith('/withdraw/')) { state.row.status = 'withdrawn'; state.row.version++ }
      else { Object.assign(state.row, request.postDataJSON()); state.row.version++; state.row.status = 'draft' }
      return route.fulfill({ json: envelope({ ...state.row }) })
    }
    if (path.endsWith('/dashboard/stats/')) return route.fulfill({ json: envelope({ totals: {}, login_trend: [], task_status: {} }) })
    return route.fulfill({ json: envelope(paged([])) })
  })
  return state
}

async function management(page: Page) {
  await page.goto('/notifications/announcements')
  await page.getByRole('radio', { name: '已发布公告', exact: true }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('radio', { name: '公告管理', exact: true })).toBeChecked()
  await page.locator('.el-radio-button').filter({ hasText: '已发布公告' }).click()
  await expect(page.getByRole('radio', { name: '已发布公告', exact: true })).toBeChecked()
  await page.locator('.el-radio-button').filter({ hasText: '公告管理' }).click()
  await expect(page.getByRole('radio', { name: '公告管理', exact: true })).toBeChecked()
  await expect(page.getByRole('cell', { name: '公告标题', exact: true })).toBeVisible()
}

test('普通用户只读共享已发布公告，正文保持纯文本且手机无溢出', async ({ page }) => {
  const state = await setup(page, false); state.row.status = 'published'
  await page.goto('/notifications/announcements')
  await expect(page.getByRole('radio', { name: '公告管理', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '新增公告' })).toHaveCount(0)
  await page.getByRole('button', { name: '详情', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('<img src=x onerror=alert(1)>')
  await expect(dialog.locator('img')).toHaveCount(0)
  expect(state.writes).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('草稿取消/关闭提示保留输入，确认丢弃不落盘', async ({ page }) => {
  const state = await setup(page); await management(page)
  await page.getByRole('button', { name: '新增公告', exact: true }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: '新增公告' })
  await dialog.getByLabel('标题', { exact: true }).fill('private announcement draft')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  const prompt = page.getByRole('dialog').filter({ hasText: '尚有未保存的修改，确定放弃吗？' })
  await prompt.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog.getByLabel('标题', { exact: true })).toHaveValue('private announcement draft')
  await dialog.locator('.el-dialog__headerbtn').click()
  await prompt.getByRole('button', { name: '确定', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(await page.evaluate(() => Object.values(localStorage).some(value => value.includes('private announcement draft')))).toBe(false)
  expect(state.writes).toBe(0)
})

test('校验无写入，提交同步锁，409保留输入，修正后保存草稿', async ({ page }) => {
  const state = await setup(page); await management(page)
  await page.getByRole('button', { name: '新增公告', exact: true }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: '新增公告' })
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('请填写公告标题和正文'); expect(state.writes).toBe(0)
  await dialog.getByLabel('标题', { exact: true }).fill('修改公告')
  await dialog.getByLabel('公告正文', { exact: true }).fill('草稿正文')
  state.status = 409
  let release!: () => void; state.delay = new Promise(resolve => { release = resolve })
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog.getByLabel('标题', { exact: true })).toBeDisabled()
  await dialog.locator('form').dispatchEvent('submit')
  expect(state.writes).toBe(1); release()
  await expect(dialog.getByRole('alert')).toContainText('保存失败，已保留输入')
  await expect(dialog.getByLabel('公告正文', { exact: true })).toHaveValue('草稿正文')
  state.status = 200; state.delay = undefined
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog).not.toBeVisible(); expect(state.writes).toBe(2)
  await expect(page.getByRole('cell', { name: '修改公告', exact: true })).toBeVisible()
})

test('发布与撤回各需二次确认，取消无写入，发布后不能编辑', async ({ page }) => {
  const state = await setup(page); await management(page)
  await page.getByRole('button', { name: '发布公告', exact: true }).click()
  const publish = page.getByRole('dialog').filter({ hasText: '确定发布公告吗？' })
  await publish.getByRole('button', { name: '取消', exact: true }).click(); expect(state.writes).toBe(0)
  await page.getByRole('button', { name: '发布公告', exact: true }).click()
  await publish.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByRole('button', { name: '撤回公告', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '撤回公告', exact: true }).click()
  const withdraw = page.getByRole('dialog').filter({ hasText: '确定撤回公告吗？' })
  await withdraw.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByRole('button', { name: '编辑', exact: true })).toBeVisible(); expect(state.writes).toBe(2)
})

test('权限撤销后的迟到保存不复活编辑窗口或泄漏草稿', async ({ page }) => {
  const state = await setup(page); await management(page)
  await page.getByRole('button', { name: '新增公告', exact: true }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: '新增公告' })
  await dialog.getByLabel('标题', { exact: true }).fill('private late title')
  await dialog.getByLabel('公告正文', { exact: true }).fill('private late body')
  let release!: () => void; state.delay = new Promise(resolve => { release = resolve })
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  state.admin = false
  const refreshed = page.waitForResponse('**/auth/me/')
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await refreshed
  await expect(dialog).not.toBeVisible()
  release()
  await expect(page.getByRole('button', { name: '新增公告', exact: true })).toHaveCount(0)
  await expect(page.getByRole('dialog').filter({ hasText: 'private late title' })).toHaveCount(0)
})

test('模块关闭禁止直接打开公告路由', async ({ page }) => {
  const state = await setup(page); state.enabled = false
  await page.goto('/notifications/announcements')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('button', { name: '新增公告', exact: true })).toHaveCount(0)
  expect(state.writes).toBe(0)
})

test('空状态与读取失败可重试，英文深色窄屏布局完整', async ({ page }) => {
  const state = await setup(page, false)
  await page.addInitScript(() => { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') })
  await page.goto('/notifications/announcements')
  await expect(page.getByRole('heading', { name: 'Announcements', exact: true })).toBeVisible()
  await expect(page.locator('.table-empty')).toBeVisible()
  state.readStatus = 503
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByText('Unable to load announcements. Try again', { exact: true })).toBeVisible()
  state.readStatus = 200; state.row.status = 'published'
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByRole('cell', { name: '公告标题', exact: true })).toBeVisible()
  await expect(page.getByText('Unable to load announcements. Try again', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Details', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('纯文本正文')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.locator('html')).toHaveClass(/dark/)
})
