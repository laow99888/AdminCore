import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3XcAAAAASUVORK5CYII=', 'base64')
const csp = readFileSync('spa-csp.conf', 'utf8').match(/Content-Security-Policy "([^"]+)"/)![1]

async function setup(page: Page, enabled = true) {
  const state = {
    profile: { id: 'member', username: 'member', email: 'm@example.com', first_name: '', last_name: '', phone: '', bio: '',
      avatar: 'https://external.example/legacy-avatar.png', profile_version: 1, has_avatar: false, avatar_enabled: enabled, permissions: ['*'] },
    conflict: false, loadFailed: false, avatarFailed: false, reads: 0, saves: [] as Record<string, unknown>[], uploads: [] as string[], removes: [] as unknown[],
  }
  await page.addInitScript(() => {
    localStorage.setItem('token', 'isolated-profile-fixture')
    const revoke = URL.revokeObjectURL.bind(URL)
    const records: string[] = []
    Object.assign(window, { avatarRevoked: records })
    URL.revokeObjectURL = value => { records.push(value); revoke(value) }
  })
  await page.route('**/settings', async route => {
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': csp } })
  })
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore' }) })
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope(state.profile) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'minimal', modules: [] }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([{ id: 'settings', name: '系统设置', path: '/settings', children: [] }, { id: 'users', name: '用户管理', path: '/users', children: [] }]) })
    if (path.endsWith('/users/')) return route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 20, total_pages: 0 } }) })
    if (path.endsWith('/auth/profile/')) {
      if (request.method() === 'GET') {
        if (state.loadFailed) return route.fulfill({ status: 503, json: { code: 503, message: '暂不可用', data: null } })
        return route.fulfill({ json: envelope(state.profile) })
      }
      state.saves.push(request.postDataJSON())
      if (state.conflict) return route.fulfill({ status: 409, json: { code: 409, message: '资料版本冲突', data: null } })
      state.profile = { ...state.profile, ...request.postDataJSON(), profile_version: state.profile.profile_version + 1 }
      return route.fulfill({ json: envelope(state.profile) })
    }
    if (path.endsWith('/auth/avatar/')) {
      expect(request.headers().authorization).toBe('Bearer isolated-profile-fixture')
      expect(request.url()).not.toContain('token=')
      if (request.method() === 'GET') {
        state.reads++
        if (state.avatarFailed) return route.fulfill({ status: 503, json: { code: 503, message: '头像不可用', data: null } })
        return route.fulfill({ contentType: 'image/png', body: png })
      }
      if (request.method() === 'POST') state.uploads.push(request.postData() || '')
      else state.removes.push(request.postDataJSON())
      state.profile = { ...state.profile, has_avatar: request.method() === 'POST', profile_version: state.profile.profile_version + 1 }
      return route.fulfill({ json: envelope(state.profile) })
    }
    return route.fulfill({ json: envelope({}) })
  })
  return state
}

test('关闭页签和关闭其他尊重未保存提示，取消后保留输入与页签', async ({ page }) => {
  await setup(page)
  await page.goto('/users')
  if (page.viewportSize()!.width <= 768) await page.getByRole('button', { name: '打开菜单' }).click()
  await page.locator('.sidebar-menu a[href="/settings"]').click()
  await page.getByLabel('名字', { exact: true }).fill('dirty-tabs')
  await page.getByRole('button', { name: '关闭页签 系统设置', exact: true }).click()
  await expect(page.getByText('尚有未保存的资料，确定放弃修改吗？')).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('dirty-tabs')
  await expect(page.locator('.navigation-tab[data-path="/settings"]')).toBeVisible()
  await page.locator('.navigation-tab[data-path="/users"]').click({ button: 'right' })
  await page.getByRole('button', { name: '关闭其他页签', exact: true }).click()
  await expect(page.getByText('尚有未保存的资料，确定放弃修改吗？')).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('.navigation-tab')).toHaveCount(3)
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('dirty-tabs')
})

test('关闭后台缓存页签不重建正在编辑的个人资料', async ({ page }) => {
  await setup(page)
  await page.route('**/logs/operation/**', route => route.fulfill({ json: envelope({ items: [], pagination: { total: 0, page: 1, page_size: 10, total_pages: 0 } }) }))
  await page.goto('/logs')
  if (page.viewportSize()!.width <= 768) await page.getByRole('button', { name: '打开菜单' }).click()
  await page.locator('.sidebar-menu a[href="/settings"]').click()
  await page.getByLabel('名字', { exact: true }).fill('keep-current-form')
  await page.getByRole('button', { name: '关闭页签 操作日志', exact: true }).click()
  await expect(page.locator('.navigation-tab[data-path="/logs"]')).toHaveCount(0)
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('keep-current-form')
})

test('资料保存白名单和版本，字段错误不发请求，手机无溢出', async ({ page }, testInfo) => {
  const state = await setup(page)
  await page.goto('/settings')
  await expect(page.getByRole('button', { name: '保存资料' })).toBeDisabled()
  await page.getByLabel('电话', { exact: true }).fill('invalid')
  await page.getByRole('button', { name: '保存资料' }).click()
  await expect(page.getByText('请输入有效电话')).toBeVisible()
  expect(state.saves).toHaveLength(0)
  await page.getByLabel('电话', { exact: true }).fill('+86 12345678')
  await page.getByLabel('名字', { exact: true }).fill('新名字')
  await page.getByLabel('个人简介').fill('个人介绍')
  await page.getByRole('button', { name: '保存资料' }).click()
  await expect(page.getByRole('button', { name: '保存资料' })).toBeDisabled()
  expect(state.saves).toEqual([{ first_name: '新名字', last_name: '', email: 'm@example.com', phone: '+86 12345678', bio: '个人介绍', profile_version: 1 }])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(await page.locator('img').evaluateAll(nodes => nodes.some(node => (node as HTMLImageElement).src.includes('external.example')))).toBe(false)
  await expect(page.getByText('资料已保存', { exact: true })).toBeHidden()
  await page.locator('main').evaluate(node => { node.scrollTop = 0 })
  await page.screenshot({ path: testInfo.outputPath('personal-profile.png'), fullPage: true })
})

test('版本冲突保留输入，重新加载需要确认', async ({ page }) => {
  const state = await setup(page); state.conflict = true
  await page.goto('/settings')
  await page.getByLabel('名字', { exact: true }).fill('未保存的名字')
  await page.getByRole('button', { name: '保存资料' }).click()
  await expect(page.getByRole('alert').filter({ hasText: '当前输入已保留' })).toBeVisible()
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('未保存的名字')
  await page.getByRole('button', { name: '重新加载资料' }).click()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('未保存的名字')
  state.profile = { ...state.profile, first_name: '其他窗口', profile_version: 2 }
  await page.getByRole('button', { name: '重新加载资料' }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('其他窗口')
})

test('上传头像保留未保存资料，共享私有 Blob，更换及删除释放资源', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/settings')
  await page.getByLabel('名字', { exact: true }).fill('未保存')
  await page.locator('input[type=file]').setInputFiles({ name: 'profile.png', mimeType: 'image/png', buffer: png })
  const images = page.locator('.private-avatar img')
  await expect(images).toHaveCount(2)
  await expect(images.first()).toHaveAttribute('src', /^blob:/)
  await expect.poll(() => state.reads).toBe(1)
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('未保存')
  expect(state.uploads[0]).toContain('name="profile_version"\r\n\r\n1')
  await page.locator('input[type=file]').setInputFiles({ name: 'new.png', mimeType: 'image/png', buffer: png })
  await expect.poll(() => state.reads).toBe(2)
  await expect.poll(() => page.evaluate(() => (window as unknown as { avatarRevoked: string[] }).avatarRevoked.length)).toBe(1)
  await page.getByRole('button', { name: '删除头像', exact: true }).click()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  expect(state.removes).toHaveLength(0)
  await page.getByRole('button', { name: '删除头像', exact: true }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(images).toHaveCount(0)
  expect(state.removes).toEqual([{ profile_version: 3 }])
  await page.getByRole('button', { name: '保存资料' }).click()
  await expect.poll(() => state.saves.length).toBe(1)
  expect(state.saves[0]!.profile_version).toBe(4)
})

test('加载和头像失败可重试，文件模块关闭禁用操作', async ({ page }) => {
  const state = await setup(page); state.loadFailed = true
  await page.goto('/settings')
  await expect(page.getByText('个人资料加载失败')).toBeVisible()
  state.loadFailed = false
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByLabel('名字', { exact: true })).toBeVisible()
  state.avatarFailed = true
  await page.locator('input[type=file]').setInputFiles({ name: 'profile.png', mimeType: 'image/png', buffer: png })
  await expect(page.getByText('头像加载失败')).toBeVisible()
  state.avatarFailed = false
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.locator('.private-avatar img')).toHaveCount(2)
  state.profile.avatar_enabled = false
  await page.reload()
  await expect(page.getByText('文件模块未启用，头像操作不可用')).toBeVisible()
  await expect(page.getByRole('button', { name: '上传头像' })).toBeDisabled()
  await expect(page.locator('.private-avatar img')).toHaveCount(0)
})

test('英文深色模式及上传校验，提交期间禁用重复操作', async ({ page }) => {
  await setup(page)
  await page.addInitScript(() => { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') })
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  let calls = 0
  await page.route('**/auth/profile/', async route => {
    if (route.request().method() === 'GET') return route.fallback()
    calls++; await held; return route.fulfill({ status: 503, json: { code: 503, message: 'failed', data: null } })
  })
  await page.goto('/settings')
  await page.locator('input[type=file]').setInputFiles({ name: 'bad.svg', mimeType: 'image/svg+xml', buffer: Buffer.from('<svg/>') })
  await expect(page.getByText('Choose a PNG, JPEG or WebP image up to 5 MiB')).toBeVisible()
  await page.getByLabel('First Name', { exact: true }).fill('fixture')
  await page.getByRole('button', { name: 'Save Profile' }).click()
  await expect(page.getByLabel('First Name', { exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Upload Picture' })).toBeDisabled()
  release()
  await expect(page.getByRole('alert').filter({ hasText: 'Check your input' })).toBeVisible()
  expect(calls).toBe(1)
  await expect(page.getByLabel('First Name', { exact: true })).toHaveValue('fixture')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('未保存资料离开有取消和确认，撤销后不再提示', async ({ page }) => {
  await setup(page)
  await page.goto('/settings')
  await page.getByLabel('名字', { exact: true }).fill('dirty')
  if (page.viewportSize()!.width < 768) await page.getByRole('button', { name: '打开菜单' }).click()
  await page.locator('a[href="/users"]').click()
  await expect(page.getByText('尚有未保存的资料，确定放弃修改吗？')).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await page.getByRole('button', { name: '撤销修改' }).click()
  await expect(page.getByText('尚有未保存的资料，确定放弃修改吗？')).toBeVisible()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('dirty')
  await page.getByRole('button', { name: '撤销修改' }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByLabel('名字', { exact: true })).toHaveValue('')
  await expect(page.getByRole('button', { name: '保存资料' })).toBeDisabled()
  if (page.viewportSize()!.width < 768) await page.getByRole('button', { name: '打开菜单' }).click()
  await page.locator('a[href="/users"]').click()
  await expect(page).toHaveURL(/\/users$/)
})

test('提交遇到凭据撤销仍跳转登录，不被忙碌或未保存提示阻断', async ({ page }) => {
  await setup(page)
  await page.route('**/auth/profile/', async route => {
    if (route.request().method() === 'GET') return route.fallback()
    return route.fulfill({ status: 401, json: { code: 401, message: '登录凭据已撤销', data: null } })
  })
  await page.goto('/settings')
  await page.getByLabel('名字', { exact: true }).fill('未保存')
  await page.getByRole('button', { name: '保存资料' }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
  await expect(page.locator('.private-avatar img')).toHaveCount(0)
})

test('切换语言后资料标签及校验即时切换，保留未保存输入', async ({ page }) => {
  const state = await setup(page)
  await page.goto('/settings')
  await page.getByLabel('电话', { exact: true }).fill('invalid')
  await page.getByRole('button', { name: '切换语言', exact: true }).click()
  await page.getByRole('menuitem', { name: 'English', exact: true }).click()
  await page.getByRole('button', { name: 'Save Profile' }).click()
  await expect(page.getByText('Enter a valid phone number')).toBeVisible()
  await expect(page.getByLabel('Phone', { exact: true })).toHaveValue('invalid')
  expect(state.saves).toHaveLength(0)
})
