import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const record = { id: 'f1', original_name: 'private-fixture.txt', file: '/files/f1/download/', file_type: 'txt', size: 7, size_display: '7 B', description: '', uploader_name: 'member', download_count: 0, created_at: '', is_deleted: true, deleted_at: '2026-10-13T10:00:00+08:00', lifecycle_version: 2 }
async function setup(page: Page, permissions = ['*'], failList = false) {
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-recycle-fixture'))
  let completed = false
  const writes: Array<{ action: string; dry_run: boolean; confirmation: string; items: unknown[] }> = []
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'member', username: 'member', is_staff: false, is_superuser: false, permissions }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/recycle_policy/')) return route.fulfill({ json: envelope({ retention_days: 45, cleanup_enabled: true }) })
    if (path.endsWith('/recycle_action/')) {
      const data = route.request().postDataJSON()
      writes.push(data)
      if (!data.dry_run) completed = true
      return route.fulfill({ json: envelope({ results: [{ id: 'f1', status: 200, message: '已完成', original_name: record.original_name, size: 7 }], dry_run: data.dry_run, succeeded: 1, failed: 0 }) })
    }
    if (path.endsWith('/recycle/')) return route.fulfill(failList ? { status: 503, json: { code: 503, message: 'fixture unavailable', data: null } } : { json: envelope({ items: completed ? [] : [record], pagination: { total: completed ? 0 : 1, page: 1, page_size: 10, total_pages: 1 } }) })
    return route.fulfill({ json: envelope({ count: 0 }) })
  })
  return writes
}

test('回收站恢复保留版本、展示逐项结果与实际保留期', async ({ page }) => {
  const writes = await setup(page)
  await page.goto('/files/recycle')
  await expect(page.getByText('软删除保留 45 天，过期文件由清理任务永久删除')).toBeVisible()
  await page.getByRole('button', { name: '恢复', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('成功 1 项，失败 0 项')).toBeVisible()
  await expect(dialog.getByText('private-fixture.txt — 已完成')).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(writes[0].items).toEqual([{ id: 'f1', lifecycle_version: 2 }])
  expect(writes[0].action).toBe('restore')
})

test('彻底删除先预览，输入确认后只提交一次，窄屏无页面溢出', async ({ page }) => {
  const writes = await setup(page)
  await page.addInitScript(() => localStorage.setItem('theme', 'dark'))
  await page.goto('/files/recycle')
  await page.getByRole('button', { name: '彻底删除', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('本次将删除 1 个文件，共 7 字节')).toBeVisible()
  await expect(dialog.getByRole('button', { name: '彻底删除', exact: true })).toBeDisabled()
  expect(writes).toHaveLength(1)
  expect(writes[0].dry_run).toBe(true)
  const bounds = await dialog.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: test.info().outputPath('recycle-preview-dark.png'), fullPage: true })
  await dialog.getByLabel('输入 DELETE 确认').fill('DELETE')
  await dialog.getByRole('button', { name: '彻底删除', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('成功 1 项，失败 0 项')).toBeVisible()
  expect(writes).toHaveLength(2)
  expect(writes[1]).toMatchObject({ action: 'purge', dry_run: false, confirmation: 'DELETE' })
})

test('只有查看权限时不显示恢复和彻底删除入口', async ({ page }) => {
  await setup(page, ['file:recycle'])
  await page.addInitScript(() => localStorage.setItem('language', 'en-US'))
  await page.goto('/files/recycle')
  await expect(page.getByText('File Recycle Bin', { exact: true })).toBeVisible()
  await expect(page.getByText(record.original_name, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /Restore|Delete|Edit/ })).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('recycle-readonly-en.png'), fullPage: true })
})

test('回收站权限缺失时路由拒绝且不请求文件数据', async ({ page }) => {
  await setup(page, [])
  let requested = false
  page.on('request', request => { if (/\/files\/(recycle|recycle_policy)\//.test(request.url())) requested = true })
  await page.goto('/files/recycle')
  await expect(page).toHaveURL(/\/403$/)
  expect(requested).toBe(false)
})

test('列表失败可以刷新恢复，空状态不残留选择', async ({ page }) => {
  await setup(page, ['*'], true)
  await page.goto('/files/recycle')
  await expect(page.getByText('回收站加载失败，请重试')).toBeVisible()
  await expect(page.getByRole('button', { name: '恢复所选', exact: true })).toBeDisabled()
  await page.route('**/api/v1/files/recycle/?*', route => route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 1 } }) }))
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByText('暂无数据')).toBeVisible()
  await expect(page.getByText('回收站加载失败，请重试')).toHaveCount(0)
})

test('恢复冲突明确展示失败并保留文件，不能显示成功', async ({ page }) => {
  await setup(page)
  await page.route('**/api/v1/files/recycle_action/', route => route.fulfill({ json: envelope({ results: [{ id: 'f1', status: 409, message: '记录已变化，请刷新后重试' }], dry_run: false, succeeded: 0, failed: 1 }) }))
  await page.goto('/files/recycle')
  await page.getByRole('button', { name: '恢复', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('成功 0 项，失败 1 项')).toBeVisible()
  await expect(page.getByRole('dialog').getByText('private-fixture.txt — 记录已变化，请刷新后重试')).toBeVisible()
  await expect(page.getByRole('table').getByText(record.original_name, { exact: true })).toBeVisible()
})

test('批量选择提交当前页文件，刷新后清空选择', async ({ page }) => {
  const writes = await setup(page)
  await page.goto('/files/recycle')
  await expect(page.getByRole('button', { name: '恢复所选', exact: true })).toBeDisabled()
  await page.locator('.el-table__body-wrapper .el-checkbox').click()
  await page.getByRole('button', { name: '恢复所选', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('成功 1 项，失败 0 项')).toBeVisible()
  expect(writes[0].items).toEqual([{ id: 'f1', lifecycle_version: 2 }])
  await page.getByRole('dialog').getByRole('button', { name: '关闭', exact: true }).click()
  await expect(page.getByRole('button', { name: '恢复所选', exact: true })).toBeDisabled()
})
