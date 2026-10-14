import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const paged = (items: unknown[]) => ({ items, pagination: { total: items.length, page: 1, page_size: 20, total_pages: 1 } })
const configRow = (key: string, value: string) => ({ key, label: key, kind: 'string', value, version: 1, minimum: 1, maximum: 100, effective: '' })
async function setup(page: Page) {
  const state = { requests: 0, status: 200, delay: undefined as Promise<void> | undefined, configs: [configRow('brand.name', 'AdminCore'), configRow('brand.tagline', 'fixture')] }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-unsaved-fixture'))
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'a1', username: 'admin', email: 'admin@example.com', is_staff: true, permissions: ['*'] }) })
    if (path.endsWith('/auth/profile/')) {
      return route.fulfill({ json: envelope({ id: 'a1', username: 'admin', email: 'admin@example.com', first_name: '', last_name: '', phone: '', bio: '', profile_version: 1, has_avatar: false, avatar_enabled: false, is_staff: true, permissions: ['*'] }) })
    }
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: 'fixture' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: ['files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization'].map(key => ({ key, enabled: true, paths: key === 'system' ? ['/system/config', '/system/dictionaries'] : key === 'data_io' ? [] : [`/${key}`], dependencies: [] })) }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'm1', name: '用户管理', path: '/users', children: [] }, { id: 'm2', name: '角色权限', path: '/roles', children: [] }]) })
    if (path.endsWith('/permissions/menus/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/organization/posts/choices/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/system/config/')) return route.fulfill({ json: envelope(state.configs) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (path.endsWith('/dashboard/stats/')) return route.fulfill({ json: envelope({ totals: {}, login_trend: [], task_status: {} }) })
    if (request.method() !== 'GET') {
      state.requests++; if (state.delay) await state.delay
      if (state.status !== 200) return route.fulfill({ status: state.status, json: { code: state.status, message: 'fixture request failed', data: null } })
      if (path.includes('/system/config/')) {
        const current = state.configs.find(row => path.endsWith(`/${row.key}/`))!
        Object.assign(current, { value: request.postDataJSON().value, version: current.version + 1 })
        return route.fulfill({ json: envelope([current]) })
      }
      return route.fulfill({ json: envelope({}) })
    }
    const items = path.endsWith('/users/') ? [{ id: 'u1', username: 'member', email: 'm@example.com', is_active: true, first_name: '', last_name: '', roles: [] }] : []
    return route.fulfill({ json: envelope(paged(items)) })
  })
  return state
}
const prompt = (page: Page) => page.getByRole('dialog').filter({ hasText: '尚有未保存的修改，确定放弃吗？' })

for (const item of [
  { path: '/users', open: /新增用户/, field: '用户名' },
  { path: '/roles', open: /新增角色/, field: '角色名' },
  { path: '/menus', open: /新增菜单/, field: '菜单名' },
  { path: '/system/dictionaries', open: /新增字典/, field: '编码' },
  { path: '/organization', open: /^新增$/, field: '部门名称' },
  { path: '/organization/posts', open: /新增岗位/, field: '岗位编码' },
  { path: '/approvals', open: /发起申请/, field: '标题' },
]) {
  test(`${item.path} 初始取消无提示，修改后 Escape/取消可保留或放弃`, async ({ page }) => {
    const state = await setup(page)
    await page.goto(item.path)
    await page.getByRole('button', { name: item.open }).click()
    const dialog = page.getByRole('dialog').first()
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await expect(dialog).not.toBeVisible(); await expect(prompt(page)).toHaveCount(0)
    await page.getByRole('button', { name: item.open }).click()
    await dialog.getByLabel(item.field, { exact: true }).fill('private_draft')
    await dialog.getByLabel(item.field, { exact: true }).press('Escape')
    await expect(prompt(page)).toBeVisible()
    await prompt(page).getByRole('button', { name: '取消', exact: true }).click()
    await expect(dialog.getByLabel(item.field, { exact: true })).toHaveValue('private_draft')
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await prompt(page).getByRole('button', { name: '确定', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    await page.getByRole('button', { name: item.open }).click()
    await expect(dialog.getByLabel(item.field, { exact: true })).toHaveValue('')
    expect(state.requests).toBe(0)
    expect(await page.evaluate(() => Object.values(localStorage).some(value => value.includes('private_draft')))).toBe(false)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('密码和资料两个草稿，关闭当前页签只确认一次，取消保持密码且语言切换保留', async ({ page }) => {
  await setup(page); await page.goto('/settings')
  await page.getByLabel('名字', { exact: true }).fill('profile-draft')
  await page.getByLabel('当前密码', { exact: true }).fill('private password draft')
  await page.getByRole('button', { name: '关闭页签 系统设置', exact: true }).click()
  await expect(prompt(page)).toBeVisible()
  await prompt(page).getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByLabel('当前密码', { exact: true })).toHaveValue('private password draft')
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('profile-draft')
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await page.getByRole('menuitem', { name: 'English', exact: true }).click()
  await expect(page.getByLabel('Current Password', { exact: true })).toHaveValue('private password draft')
  await expect(page.getByLabel('First Name', { exact: true })).toHaveValue('profile-draft')
})

test('重置密码的 X/取消保护输入；提交期间不能误关闭且失败保留草稿', async ({ page }) => {
  const state = await setup(page); state.status = 409
  let release!: () => void; state.delay = new Promise(resolve => { release = resolve })
  await page.goto('/users'); await page.getByRole('button', { name: '重置密码', exact: true }).click()
  const dialog = page.getByRole('dialog').first()
  await dialog.getByLabel('新密码', { exact: true }).fill('FixtureOnly123!')
  await dialog.locator('.el-dialog__headerbtn').click(); await expect(prompt(page)).toBeVisible()
  await prompt(page).getByRole('button', { name: '取消', exact: true }).click()
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog.getByLabel('新密码', { exact: true })).toBeDisabled()
  await expect(dialog.getByRole('button', { name: '取消', exact: true })).toBeDisabled()
  await dialog.locator('.el-dialog__headerbtn').click(); await expect(dialog).toBeVisible()
  expect(state.requests).toBe(1); release()
  await expect(dialog.getByRole('button', { name: '确认', exact: true })).toBeEnabled()
  await expect(dialog.getByLabel('新密码', { exact: true })).toHaveValue('FixtureOnly123!')
})

test('系统参数逐项保存不会清掉其他字段的草稿，刷新取消保持输入', async ({ page }) => {
  const state = await setup(page); await page.goto('/system/config')
  await page.getByLabel('brand.name', { exact: true }).fill('saved brand')
  await page.getByLabel('brand.tagline', { exact: true }).fill('pending tagline')
  await page.locator('.el-form-item').filter({ has: page.getByLabel('brand.name', { exact: true }) }).getByRole('button', { name: '保存', exact: true }).click()
  await expect.poll(() => state.requests).toBe(1)
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(prompt(page)).toBeVisible(); await prompt(page).getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByLabel('brand.tagline', { exact: true })).toHaveValue('pending tagline')
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await prompt(page).getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByLabel('brand.name', { exact: true })).toHaveValue('saved brand')
  await expect(page.getByLabel('brand.tagline', { exact: true })).toHaveValue('fixture')
})

test('参数草稿语言切换先确认，取消保留原语言和输入；批准后重建不双提示', async ({ page }) => {
  await setup(page); await page.goto('/system/config')
  await page.getByLabel('brand.name', { exact: true }).fill('private_draft')
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await page.getByRole('menuitem', { name: 'English', exact: true }).click()
  await expect(prompt(page)).toBeVisible(); await prompt(page).getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByLabel('brand.name', { exact: true })).toHaveValue('private_draft')
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await page.getByRole('menuitem', { name: 'English', exact: true }).click()
  await expect(prompt(page)).toBeVisible(); await prompt(page).getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeVisible()
  await expect(page.getByLabel('brand.name', { exact: true })).toHaveValue('AdminCore')
  await expect(prompt(page)).toHaveCount(0)
})

test('提交期间凭据被撤销，安全跳转登录不被草稿/忙碌阻断', async ({ page }) => {
  const state = await setup(page); state.status = 401
  await page.goto('/users'); await page.getByRole('button', { name: /新增用户/ }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('用户名', { exact: true }).fill('fixture_member')
  await dialog.getByLabel('邮箱', { exact: true }).fill('fixture@example.com')
  await dialog.getByLabel('密码', { exact: true }).fill('FixtureOnly123!')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/); await expect(prompt(page)).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
})
