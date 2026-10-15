import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const paged = (items: unknown[]) => envelope({ items, pagination: { total: items.length, page: 1, page_size: 100, total_pages: 1 } })
const baseUser = { id: 'u1', username: 'member', email: 'm***@example.test', phone: '', first_name: 'original', last_name: '', is_active: true, version: 1, roles: [], created_at: '2026-10-16T00:00:00Z' }
const baseRole = { id: 'r1', name: 'original', description: '', is_active: true, version: 1, permissions: [] }
const baseMenu = { id: 'm1', name: 'original', path: '/users', icon: 'users', parent: null, permission: null, order: 0, is_visible: true, children: [], version: 1 }
const baseDictionary = { id: 'd1', code: 'fixture', name: 'original', description: '', is_active: true, items: [], version: 1 }
const baseDepartment = { id: 'o1', name: 'original', parent: null, order: 0, is_active: true, version: 1 }
const basePost = { id: 'p1', code: 'editor', name: 'original', description: 'original description', order: 0, is_active: true, version: 1 }
const baseExample = { id: 'e1', title: 'original', notes: '<script>literal notes</script>', status: 'open', priority: 'normal', creator: 'a1', creator_name: 'admin', version: 1 }
const cases = [
  { route: '/users', api: '/users/u1/', label: '名字', field: 'first_name', row: baseUser },
  { route: '/roles', api: '/permissions/roles/r1/', label: '角色名', field: 'name', row: baseRole },
  { route: '/menus', api: '/permissions/menus/m1/', label: '菜单名', field: 'name', row: baseMenu },
  { route: '/system/dictionaries', api: '/system/dictionaries/d1/', label: '名称', field: 'name', row: baseDictionary },
  { route: '/organization', api: '/organization/departments/o1/', label: '部门名称', field: 'name', row: baseDepartment },
  { route: '/organization/posts', api: '/organization/posts/p1/', label: '岗位名称', field: 'name', row: basePost },
  { route: '/example', api: '/example/items/e1/', label: '工单标题', field: 'title', row: baseExample },
]

async function setup(page: Page, item: typeof cases[number], inspectFailure = false) {
  let row = { ...item.row } as Record<string, any>
  const writes: Record<string, unknown>[] = []
  let reads = 0
  await page.addInitScript(() => { localStorage.setItem('token', 'isolated-edit-version-fixture'); localStorage.setItem('locale', 'zh-CN') })
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    const method = route.request().method()
    if (path === '/modules/') return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [{ key: 'organization', title: '组织', enabled: true, paths: ['/organization'], dependencies: [] }, { key: 'example', title: '示例', enabled: true, paths: ['/example'], dependencies: [] }] }) })
    if (path === '/auth/me/') return route.fulfill({ json: envelope({ id: 'a1', username: 'admin', is_staff: true, is_superuser: true, permissions: ['*'] }) })
    if (path === '/permissions/menus/my_menu/') return route.fulfill({ json: envelope([baseMenu]) })
    if (path === '/notifications/unread_count/') return route.fulfill({ json: envelope({ count: 0 }) })
    if (path === item.api) {
      if (method === 'PATCH') {
        const payload = route.request().postDataJSON(); writes.push(payload)
        if (writes.length === 1) row = { ...row, version: 2, [item.field]: 'server latest' }
        if (payload.version !== row.version) return route.fulfill({ status: 409, json: { code: 409, message: 'conflict', data: null } })
        row = { ...row, ...payload, version: row.version + 1 }
        return route.fulfill({ json: envelope(row) })
      }
      reads++
      if (inspectFailure && reads === 1) return route.fulfill({ status: 403, json: { code: 403, message: 'forbidden', data: null } })
      return route.fulfill({ json: envelope(row) })
    }
    if (path === '/users/') return route.fulfill({ json: paged([baseUser]) })
    if (path === '/permissions/roles/') return route.fulfill({ json: paged([baseRole]) })
    if (path === '/permissions/menus/') return route.fulfill({ json: paged([baseMenu]) })
    if (path === '/permissions/permissions/') return route.fulfill({ json: paged([]) })
    if (path === '/system/dictionaries/') return route.fulfill({ json: paged([baseDictionary]) })
    if (path === '/organization/departments/') return route.fulfill({ json: paged([baseDepartment]) })
    if (path === '/organization/posts/') return route.fulfill({ json: paged([basePost]) })
    if (path === '/example/items/') return route.fulfill({ json: paged([baseExample]) })
    return route.fulfill({ json: envelope({}) })
  })
  return { writes }
}

for (const item of cases) test(`${item.route} 冲突保留输入，同窗比较后显式载入并用新版本提交`, async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message))
  const { writes } = await setup(page, item)
  await page.goto(item.route)
  await page.getByRole('button', { name: '编辑', exact: true }).first().click()
  const dialog = page.getByRole('dialog')
  const input = dialog.getByLabel(item.label, { exact: true })
  const save = dialog.getByRole('button', { name: item.route === '/example' ? '保存' : '确认', exact: true })
  await input.fill('local draft')
  await save.click()
  const panel = dialog.getByRole('region', { name: '编辑冲突' })
  await expect(panel).toBeVisible(); await expect(input).toHaveValue('local draft')
  await expect(save).toBeDisabled()
  expect(writes).toHaveLength(1); expect(writes[0]!.version).toBe(1)
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.getByRole('table')).toContainText('server latest')
  await expect(panel.getByRole('table')).toContainText('local draft')
  await expect(input).toHaveValue('local draft'); expect(writes).toHaveLength(1)
  await panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true }).click()
  await expect(input).toHaveValue('server latest'); await expect(panel).not.toBeVisible()
  await input.fill('reviewed new value')
  await save.click()
  await expect(dialog).not.toBeVisible()
  expect(writes).toHaveLength(2); expect(writes[1]!.version).toBe(2)
  expect(writes[1]![item.field]).toBe('reviewed new value')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(errors).toEqual([])
})

test('最新值加载失败保留输入，可显式重试且不提前换版本', async ({ page }) => {
  const item = cases[1]!, { writes } = await setup(page, item, true)
  await page.goto(item.route); await page.getByRole('button', { name: '编辑', exact: true }).first().click()
  const dialog = page.getByRole('dialog'), input = dialog.getByLabel('角色名', { exact: true })
  await input.fill('retained'); await dialog.getByRole('button', { name: '确认', exact: true }).click()
  const panel = dialog.getByRole('region', { name: '编辑冲突' })
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.getByRole('alert').last()).toContainText('最新值加载失败或已无权限')
  await expect(input).toHaveValue('retained'); expect(writes).toHaveLength(1)
  await expect(panel.getByRole('button', { name: '载入服务器最新值（替换当前输入）', exact: true })).toHaveCount(0)
  await panel.getByRole('button', { name: '查看服务器最新值', exact: true }).click()
  await expect(panel.getByRole('table')).toContainText('server latest')
  await expect(input).toHaveValue('retained'); expect(writes).toHaveLength(1)
})
