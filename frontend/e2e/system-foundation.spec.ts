import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const config = { key: 'files.retention_days', label: '软删除文件保留天数', kind: 'integer', value: 30, default: 30, version: 0, minimum: 1, maximum: 3650, effective: '下次读取生效；品牌在页面刷新后生效' }
async function setup(page: Page, minimal = false, failModules = false) {
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-foundation-fixture'))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: '示例产品', tagline: '示例说明' }) })
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'a1', username: 'admin', is_staff: true, is_superuser: true, permissions: ['*'] }) })
    if (path.endsWith('/modules/')) return route.fulfill(failModules ? { status: 503, json: envelope(null) } : { json: envelope({ contract_version: 1, preset: minimal ? 'minimal' : 'standard', modules: ['files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization'].map(key => ({ key, enabled: !minimal, paths: key === 'system' ? ['/system/config', '/system/dictionaries'] : key === 'data_io' ? [] : [`/${key}`], dependencies: [] })) }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'm1', name: '文件管理', path: '/files', children: [] }, { id: 'm2', name: '系统参数', path: '/system/config', children: [] }]) })
    if (path.endsWith('/dashboard/stats/')) return route.fulfill({ json: envelope({ totals: { users: 1, today_logins: 1, today_operations: 0 }, login_trend: [], task_status: {} }) })
    if (path.endsWith('/system/config/')) return route.fulfill({ json: envelope([config]) })
    if (path.endsWith('/system/dictionaries/')) return route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 20, total_pages: 1 } }) })
    if (path.endsWith('/users/')) return route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 20, total_pages: 1 } }) })
    return route.fulfill({ json: envelope({ count: 0 }) })
  })
}

test('关闭模块阻止直接访问、隐藏菜单通知和导入导出', async ({ page }) => {
  await setup(page, true)
  const requests: string[] = []
  page.on('request', request => requests.push(new URL(request.url()).pathname))
  await page.goto('/files')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('button', { name: '通知中心', exact: true })).toHaveCount(0)
  await expect(page.locator('nav').getByText('文件管理')).toHaveCount(0)
  await page.goto('/users')
  await expect(page.getByRole('button', { name: '导入', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '导出', exact: true })).toHaveCount(0)
  expect(requests.some(path => path.includes('/notifications/') || path.includes('/files/'))).toBe(false)
})

test('模块契约加载失败阻断业务并提供重试', async ({ page }) => {
  await setup(page, false, true)
  await page.goto('/users')
  await expect(page).toHaveURL(/\/unavailable$/)
  await expect(page.getByText('服务暂时不可用')).toBeVisible()
  await expect(page.getByRole('button', { name: '重试', exact: true })).toBeVisible()
})

test('畸形模块契约阻断业务入口', async ({ page }) => {
  await setup(page)
  await page.route('**/api/v1/modules/', route => route.fulfill({ json: envelope({ contract_version: 1, modules: [{ key: 'files', enabled: true }] }) }))
  await page.goto('/files')
  await expect(page).toHaveURL(/\/unavailable$/)
})

test('系统参数携带版本保存，冲突保留输入', async ({ page }) => {
  await setup(page)
  await page.route('**/api/v1/system/config/files.retention_days/', route => route.fulfill({ status: 409, json: envelope(null) }))
  await page.goto('/system/config')
  await expect(page.getByLabel('软删除文件保留天数')).toBeVisible()
  const input = page.getByRole('spinbutton')
  await input.fill('45')
  const request = page.waitForRequest(request => request.method() === 'PATCH')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  expect((await request).postDataJSON()).toEqual({ value: 45, version: 0 })
  await expect(page.getByRole('region', { name: '编辑冲突' })).toBeVisible()
  await expect(input).toHaveValue('45')
  await expect(page.getByRole('button', { name: '保存', exact: true })).toBeDisabled()
})

test('字典新增校验、字段提交与窄屏暗色弹窗', async ({ page }, testInfo) => {
  await setup(page)
  await page.goto('/system/dictionaries')
  await page.getByRole('button', { name: '切换到深色模式', exact: true }).click()
  await page.getByRole('button', { name: '新增字典', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog.getByText('请填写有效编码和名称')).toBeVisible()
  await dialog.getByLabel('编码', { exact: true }).fill('customer_level')
  await dialog.getByLabel('名称', { exact: true }).fill('客户等级')
  await dialog.getByRole('button', { name: '添加字典项' }).click()
  await dialog.getByRole('group', { name: '字典项 1' }).getByLabel('名称', { exact: true }).fill('普通')
  await dialog.getByRole('group', { name: '字典项 1' }).getByLabel('值', { exact: true }).fill('normal')
  const bounds = await dialog.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.screenshot({ path: testInfo.outputPath('dictionary-dark.png'), fullPage: true })
  const request = page.waitForRequest(request => request.method() === 'POST' && request.url().includes('/system/dictionaries/'))
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  expect((await request).postDataJSON()).toMatchObject({ code: 'customer_level', version: 0, items: [{ label: '普通', value: 'normal', is_active: true, order: 0 }] })
  await expect(dialog).not.toBeVisible()
})

test('公共品牌名称与说明应用到登录页和标题', async ({ page }) => {
  await page.route('**/api/v1/brand/', route => route.fulfill({ json: envelope({ name: '示例产品', tagline: '示例说明' }) }))
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '示例产品' })).toBeVisible()
  await expect(page.getByText('示例说明')).toBeVisible()
  await expect(page).toHaveTitle('示例产品')
})

const paged = (items: unknown[]) => envelope({ items, pagination: { total: items.length, page: 1, page_size: 100, total_pages: 1 } })
const departments = [
  { id: 'd1', name: '总部', parent: null, order: 0, is_active: true, version: 1 },
  { id: 'd2', name: '团队', parent: 'd1', order: 0, is_active: true, version: 1 },
  { id: 'd3', name: '外部', parent: null, order: 0, is_active: true, version: 1 },
]
async function setupOrganization(page: Page, failReferences = false) {
  await setup(page)
  await page.route('**/api/v1/permissions/roles/**', route => route.fulfill(failReferences ? { status: 503, json: envelope(null) } : { json: paged([{ id: 'r1', name: '业务角色' }]) }))
  await page.route('**/api/v1/organization/**', route => route.fulfill({ json: paged(new URL(route.request().url()).pathname.endsWith('/departments/') ? departments : []) }))
}

test('部门编辑排除自身及下级，版本冲突保留输入', async ({ page }, testInfo) => {
  await setupOrganization(page)
  await page.goto('/organization')
  await page.getByRole('row').filter({ hasText: '总部' }).getByRole('button', { name: '编辑', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('上级部门').focus()
  await dialog.getByLabel('上级部门').press('ArrowDown')
  await expect(page.getByRole('option', { name: '总部', exact: true })).toHaveCount(0)
  await expect(page.getByRole('option', { name: '团队', exact: true })).toHaveCount(0)
  await page.getByRole('option', { name: '外部', exact: true }).click()
  await dialog.getByLabel('部门名称').fill('新总部')
  await page.route('**/api/v1/organization/departments/d1/', route => route.fulfill({ status: 409, json: envelope(null) }))
  const request = page.waitForRequest(request => request.method() === 'PATCH')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  expect((await request).postDataJSON()).toMatchObject({ parent: 'd3', name: '新总部', version: 1 })
  await expect(dialog.getByRole('region', { name: '编辑冲突' })).toBeVisible()
  await expect(dialog.getByLabel('部门名称')).toHaveValue('新总部')
  const bounds = await dialog.boundingBox()
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.screenshot({ path: testInfo.outputPath('organization-conflict.png'), fullPage: true })
})

test('自定义数据范围必须选择角色和部门，提交声明版本', async ({ page }) => {
  await setupOrganization(page)
  await page.goto('/organization')
  await page.getByRole('tab', { name: '角色数据范围', exact: true }).click()
  await page.getByRole('button', { name: '新增', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog.getByText('请选择角色和授权范围')).toBeVisible()
  await dialog.getByLabel('角色', { exact: true }).focus()
  await dialog.getByLabel('角色', { exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '业务角色', exact: true }).click()
  await dialog.getByLabel('数据范围', { exact: true }).focus()
  await dialog.getByLabel('数据范围', { exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '自定义部门', exact: true }).click()
  await dialog.getByLabel('授权部门', { exact: true }).focus()
  await dialog.getByLabel('授权部门', { exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '团队', exact: true }).click()
  await dialog.getByLabel('资源', { exact: true }).focus()
  await dialog.getByLabel('资源', { exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '用户', exact: true }).click()
  const request = page.waitForRequest(request => request.method() === 'POST')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  expect((await request).postDataJSON()).toEqual({ role: 'r1', resource: 'user', scope: 'custom', departments: ['d2'], version: 0 })
  await expect(dialog).not.toBeVisible()
})

test('组织页切换不同数据结构时立即清理旧行，不触发全局错误边界', async ({ page }) => {
  await setupOrganization(page)
  let releaseScopes!: () => void
  const hold = new Promise<void>(resolve => { releaseScopes = resolve })
  await page.route('**/api/v1/organization/scopes/**', async route => {
    await hold
    await route.fulfill({ json: paged([{ id: 'scope-1', role_name: '业务角色', resource: 'user', scope: 'self' }]) })
  })
  await page.goto('/organization')
  await expect(page.getByRole('row').filter({ hasText: '总部' })).toBeVisible()
  const requested = page.waitForRequest(request => new URL(request.url()).pathname.endsWith('/organization/scopes/'))
  await page.getByRole('tab', { name: '角色数据范围', exact: true }).click()
  await requested
  await expect(page.getByRole('row').filter({ hasText: '总部' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '页面发生错误', exact: true })).toHaveCount(0)
  releaseScopes()
  await expect(page.getByRole('row').filter({ hasText: '业务角色' })).toContainText('本人')
})

test('组织页前一标签迟到的成功响应不能覆盖新标签；最新请求仍可正常显示', async ({ page }) => {
  await setupOrganization(page)
  let releaseMemberships!: () => void
  const hold = new Promise<void>(resolve => { releaseMemberships = resolve })
  await page.route('**/api/v1/organization/memberships/**', async route => {
    await hold
    await route.fulfill({ json: paged([{ id: 'membership-1', username: '迟到人员', department_name: '团队' }]) })
  })
  await page.route('**/api/v1/organization/scopes/**', route => route.fulfill({ json: paged([{ id: 'scope-1', role_name: '最新角色', resource: 'file', scope: 'all' }]) }))
  await page.goto('/organization')
  await expect(page.getByRole('row').filter({ hasText: '总部' })).toBeVisible()
  const requested = page.waitForRequest(request => new URL(request.url()).pathname.endsWith('/organization/memberships/'))
  await page.getByRole('tab', { name: '人员归属', exact: true }).click()
  await requested
  await page.getByRole('tab', { name: '角色数据范围', exact: true }).click()
  await expect(page.getByRole('row').filter({ hasText: '最新角色' })).toContainText('全部')
  const response = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/organization/memberships/'))
  releaseMemberships()
  await response
  // Let the completed request settle through Vue's normal rendering queue before assertions.
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
  await expect(page.getByRole('row').filter({ hasText: '最新角色' })).toContainText('全部')
  await expect(page.getByRole('row').filter({ hasText: '迟到人员' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '页面发生错误', exact: true })).toHaveCount(0)
})

test('组织页前一标签迟到的失败响应不会清掉新标签加载状态或显示旧错误', async ({ page }) => {
  await setupOrganization(page)
  let releaseMemberships!: () => void
  let releaseScopes!: () => void
  const membershipsHold = new Promise<void>(resolve => { releaseMemberships = resolve })
  const scopesHold = new Promise<void>(resolve => { releaseScopes = resolve })
  await page.route('**/api/v1/organization/memberships/**', async route => {
    await membershipsHold
    await route.fulfill({ status: 503, json: envelope(null) })
  })
  await page.route('**/api/v1/organization/scopes/**', async route => {
    await scopesHold
    await route.fulfill({ json: paged([{ id: 'scope-1', role_name: '等待后角色', resource: 'task', scope: 'department' }]) })
  })
  await page.goto('/organization')
  await expect(page.getByRole('row').filter({ hasText: '总部' })).toBeVisible()
  const membershipRequested = page.waitForRequest(request => new URL(request.url()).pathname.endsWith('/organization/memberships/'))
  await page.getByRole('tab', { name: '人员归属', exact: true }).click()
  await membershipRequested
  const scopeRequested = page.waitForRequest(request => new URL(request.url()).pathname.endsWith('/organization/scopes/'))
  await page.getByRole('tab', { name: '角色数据范围', exact: true }).click()
  await scopeRequested
  const response = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/organization/memberships/'))
  releaseMemberships()
  await response
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
  await expect(page.getByRole('alert').filter({ hasText: '组织数据加载失败' })).toHaveCount(0)
  await expect(page.locator('.base-table .el-loading-mask')).toBeVisible()
  releaseScopes()
  await expect(page.getByRole('row').filter({ hasText: '等待后角色' })).toContainText('本部门')
})

test('组织选项失败禁用编辑；非管理员不能直接访问组织入口', async ({ page }) => {
  await setupOrganization(page, true)
  await page.goto('/organization')
  await expect(page.getByRole('button', { name: '新增', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '重新加载选项', exact: true })).toBeVisible()
  await page.route('**/api/v1/auth/me/', route => route.fulfill({ json: envelope({ id: 'u1', username: 'member', permissions: ['user:read'] }) }))
  await page.reload()
  await expect(page).toHaveURL(/\/403$/)
})

test('已有页面在刷新权限后撤下访问权，英文界面有完整基础文案', async ({ page }) => {
  await setupOrganization(page)
  await page.addInitScript(() => localStorage.setItem('language', 'en-US'))
  await page.goto('/system/dictionaries')
  await page.getByRole('button', { name: 'Add Dictionary', exact: true }).click()
  await expect(page.getByRole('dialog').getByLabel('Code', { exact: true })).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.route('**/api/v1/auth/me/', route => route.fulfill({ json: envelope({ id: 'u1', username: 'member', permissions: ['user:read'] }) }))
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page).toHaveURL(/\/403$/)
  await expect(page.getByText('You do not have access to this page', { exact: true })).toBeVisible()
})

test('单项参数保存保留其他未提交输入，Logo 上传和移除携带版本', async ({ page }) => {
  await setup(page)
  const name = { ...config, key: 'brand.name', label: '产品名称', kind: 'string', value: '示例产品', minimum: 1, maximum: 40 }
  let logo = { ...config, key: 'brand.logo', label: '产品 Logo', kind: 'image', value: '', minimum: 0, maximum: 280000 }
  await page.route('**/api/v1/system/config/', route => route.fulfill({ json: envelope([config, name, logo]) }))
  await page.route('**/api/v1/system/config/brand.logo/', route => {
    logo = { ...logo, value: route.request().postDataJSON().value, version: logo.version + 1 }
    return route.fulfill({ json: envelope([logo]) })
  })
  await page.route('**/api/v1/brand/', route => route.fulfill({ json: envelope({ name: '示例产品', tagline: '说明', logo: logo.value }) }))
  await page.goto('/system/config')
  await page.getByLabel('产品名称', { exact: true }).fill('未提交的名字')
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64')
  await page.getByLabel('选择 Logo 图片').setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: png })
  const group = page.locator('.el-form-item').filter({ has: page.getByLabel('选择 Logo 图片') })
  const request = page.waitForRequest(request => request.method() === 'PATCH')
  await group.getByRole('button', { name: '保存', exact: true }).click()
  expect((await request).postDataJSON()).toMatchObject({ version: 0, value: 'data:image/png;base64,' + png.toString('base64') })
  await expect(page.getByLabel('产品名称', { exact: true })).toHaveValue('未提交的名字')
  await expect(group.getByRole('button', { name: '保存', exact: true })).toBeEnabled()
  await group.getByRole('button', { name: '移除 Logo', exact: true }).click()
  const removal = page.waitForRequest(request => request.method() === 'PATCH')
  await group.getByRole('button', { name: '保存', exact: true }).click()
  expect((await removal).postDataJSON()).toEqual({ version: 1, value: '' })
})

test('认证信息服务故障进入可重试页面，保留令牌且不循环跳转', async ({ page }) => {
  await setup(page)
  await page.route('**/api/v1/auth/me/', route => route.fulfill({ status: 503, json: envelope(null) }))
  await page.goto('/users')
  await expect(page).toHaveURL(/\/unavailable$/)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBe('isolated-foundation-fixture')
})

test('可见页面定时刷新权限，不需要重新登录或聚焦', async ({ page }) => {
  await page.clock.install()
  await setup(page)
  await page.goto('/system/config')
  await expect(page.getByLabel('软删除文件保留天数')).toBeVisible()
  await page.route('**/api/v1/auth/me/', route => route.fulfill({ json: envelope({ id: 'u1', username: 'member', permissions: ['user:read'] }) }))
  await page.clock.fastForward(30050)
  await expect(page).toHaveURL(/\/403$/)
})

test('人员归属使用搜索选择用户，保存携带版本', async ({ page }) => {
  await setupOrganization(page)
  await page.route('**/api/v1/users/**', route => route.fulfill({ json: paged([{ id: 'u2', username: '业务人员' }]) }))
  await page.goto('/organization')
  await page.getByRole('tab', { name: '人员归属', exact: true }).click()
  await page.getByRole('button', { name: '新增', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('用户', { exact: true }).fill('业务')
  await page.getByRole('option', { name: '业务人员', exact: true }).click()
  await dialog.getByLabel('部门', { exact: true }).focus()
  await dialog.getByLabel('部门', { exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: '团队', exact: true }).click()
  const request = page.waitForRequest(request => request.method() === 'POST')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  expect((await request).postDataJSON()).toEqual({ user: 'u2', department: 'd2', version: 0 })
  await expect(dialog).not.toBeVisible()
})
