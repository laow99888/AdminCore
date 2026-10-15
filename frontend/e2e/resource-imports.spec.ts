import { expect, test, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const emptyPage = envelope({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 0 } })
type Resource = 'roles' | 'posts'
const resourcePages: [string, Resource][] = [['/roles', 'roles'], ['/organization/posts', 'posts']]

async function setup(page: Page) {
  const state = { permissions: ['*'], staff: true, enabled: true, fail: false, hold: undefined as Promise<void> | undefined,
    imports: [] as { body: string; authorization: string | undefined }[], templates: [] as string[] }
  await page.addInitScript(() => {
    localStorage.setItem('token', 'isolated-resource-import')
    localStorage.setItem('refreshToken', 'isolated-resource-import-refresh')
    localStorage.setItem('language', 'zh-CN')
  })
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'import-owner', username: 'importer', is_staff: state.staff, permissions: state.permissions }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [
      { key: 'data_io', title: '数据导入导出', enabled: state.enabled, dependencies: [], paths: [] },
      { key: 'organization', title: '组织管理', enabled: true, dependencies: [], paths: ['/organization'] },
    ] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/data-io/template/')) {
      state.templates.push(url.searchParams.get('resource') || '')
      expect(request.headers().authorization).toBe('Bearer isolated-resource-import')
      expect(url.searchParams.has('token')).toBe(false)
      return route.fulfill({ contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', body: 'isolated-template-fixture' })
    }
    if (path.endsWith('/data-io/import/')) {
      expect(request.method()).toBe('POST')
      expect(request.headers()['content-type']).toContain('multipart/form-data')
      state.imports.push({ body: request.postDataBuffer()?.toString('utf8') || '', authorization: request.headers().authorization })
      if (state.hold) await state.hold
      if (state.fail) return route.fulfill({ status: 400, json: { code: 400, message: '导入夹具失败，请检查表头后重试', data: null } })
      return route.fulfill({ status: 202, json: envelope({ id: 'isolated-import-task' }) })
    }
    return route.fulfill({ json: emptyPage })
  })
  return state
}

const controls = (page: Page) => page.getByRole('group', { name: '资源导入', exact: true })
async function selectCSV(page: Page, resource: Resource) {
  const chooser = page.waitForEvent('filechooser')
  await controls(page).getByRole('button', { name: '导入', exact: true }).click()
  const contents = resource === 'roles' ? 'name,description\nimport_fixture,fixture description\n' : 'code,name,description\nimport_fixture,Import fixture,fixture description\n'
  await (await chooser).setFiles({ name: `${resource}-fixture.csv`, mimeType: 'text/csv', buffer: Buffer.from(contents) })
  return page.getByRole('dialog', { name: '确认导入', exact: true })
}

test('角色与岗位模板下载，CSV选择后确认只提交一次，等待期间控件禁用', async ({ page }, info) => {
  const state = await setup(page)
  for (const [path, resource] of resourcePages) {
    await page.goto(path)
    const group = controls(page)
    await expect(group.getByRole('button', { name: '导入模板', exact: true })).toBeEnabled()
    const download = page.waitForEvent('download')
    await group.getByRole('button', { name: '导入模板', exact: true }).click()
    expect((await download).suggestedFilename()).toBe(`import-template-${resource}.xlsx`)
    expect(state.templates.at(-1)).toBe(resource)
    const dialog = await selectCSV(page, resource)
    await expect(dialog).toContainText('只新增记录，不覆盖已有记录')
    await expect(group.getByRole('button', { name: '导入模板', exact: true })).toBeDisabled()
    await expect(group.getByRole('button', { name: '导入', exact: true })).toBeDisabled()
    let release!: () => void
    state.hold = new Promise(resolve => { release = resolve })
    const before = state.imports.length
    await dialog.getByRole('button', { name: '导入', exact: true }).click()
    await expect.poll(() => state.imports.length).toBe(before + 1)
    await group.getByRole('button', { name: '导入', exact: true }).evaluate(button => button.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(state.imports).toHaveLength(before + 1)
    const sent = state.imports.at(-1)!
    expect(sent.authorization).toBe('Bearer isolated-resource-import')
    expect(sent.body).toContain(`name="resource"\r\n\r\n${resource}`)
    expect(sent.body).toContain(`filename="${resource}-fixture.csv"`)
    release(); state.hold = undefined
    await expect(page.getByText('导入任务已提交，请稍后在任务中心查看结果', { exact: true }).last()).toBeVisible()
    await expect(group.getByRole('button', { name: '导入', exact: true })).toBeEnabled()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`${resource}-import.png`), fullPage: true })
  }
})

test('取消不提交；后端错误明确显示并可重新选择相同CSV重试', async ({ page }) => {
  const state = await setup(page)
  for (const [path, resource] of resourcePages) {
    await page.goto(path)
    const before = state.imports.length
    let dialog = await selectCSV(page, resource)
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    expect(state.imports).toHaveLength(before)
    state.fail = true
    dialog = await selectCSV(page, resource)
    await dialog.getByRole('button', { name: '导入', exact: true }).click()
    await expect(controls(page).getByRole('alert')).toHaveText('导入夹具失败，请检查表头后重试')
    await expect(controls(page).getByRole('button', { name: '导入', exact: true })).toBeEnabled()
    state.fail = false
    dialog = await selectCSV(page, resource)
    await dialog.getByRole('button', { name: '导入', exact: true }).click()
    await expect.poll(() => state.imports.length).toBe(before + 2)
    await expect(controls(page).getByRole('alert')).toHaveCount(0)
    await expect(controls(page).getByRole('button', { name: '导入', exact: true })).toBeEnabled()
  }
})

test('缺导入或资源写权限、普通成员、数据模块关闭时隐藏入口', async ({ page }) => {
  const state = await setup(page)
  const readOnly = ['role:read', 'post:read']
  for (const permissions of [readOnly, [...readOnly, 'data_io:import'], [...readOnly, 'role:update', 'post:update']]) {
    state.permissions = permissions
    for (const [path] of resourcePages) {
      await page.goto(path)
      await expect(page.getByText('暂无数据', { exact: true })).toBeVisible()
      await expect(controls(page)).toHaveCount(0)
    }
  }
  state.permissions = ['*']; state.staff = false
  await page.goto('/roles')
  await expect(page.getByText('暂无数据', { exact: true })).toBeVisible()
  await expect(controls(page)).toHaveCount(0)
  state.staff = true; state.enabled = false
  for (const [path] of resourcePages) {
    await page.goto(path)
    await expect(page.getByText('暂无数据', { exact: true })).toBeVisible()
    await expect(controls(page)).toHaveCount(0)
  }
  expect(state.imports).toHaveLength(0)
  expect(state.templates).toHaveLength(0)
})
