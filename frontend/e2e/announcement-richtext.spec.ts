import { test, expect, type Page, type Locator } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })
const paged = (items: unknown[]) => ({ items, pagination: { total: items.length, page: 1, page_size: 20, total_pages: 1 } })
const attack = '<p onclick="window.__richAttack=1" style="color:red" class="danger" id="pollute">安全正文</p><script>window.__richAttack=2</script><style>discard-style-marker</style><iframe>discard-frame-marker</iframe><svg><text>discard-svg-marker</text></svg><math><mtext>discard-math-marker</mtext></math><img src="https://attacker.invalid/pixel" onerror="window.__richAttack=3"><a href="javascript:alert(1)">恶意链接</a><a href="https://user:pass@example.test/">凭据链接</a><a href="//attacker.invalid/x">相对链接</a><a href="https://example.test/a%0ab">编码控制链接</a><a href="https://example.test/guide" target="_blank" ping="https://attacker.invalid/ping">安全链接</a>'

async function setup(page: Page, admin = true) {
  const state = { admin, enabled: true, writes: [] as Record<string, unknown>[], delay: undefined as Promise<void> | undefined,
    row: { id: 'rich-announcement-1', title: '富文本公告', content: '<p>已有<strong>正文</strong></p>', content_format: 'html' as string | undefined,
      status: 'draft', version: 1, published_at: null as string | null, created_at: '2026-10-14T00:00:00Z', updated_at: '2026-10-14T00:00:00Z' } }
  await page.addInitScript(() => localStorage.setItem('token', 'isolated-richtext-fixture'))
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'rich-actor', username: state.admin ? 'admin' : 'member', is_staff: state.admin, permissions: state.admin ? ['*'] : [] }) })
    if (path.endsWith('/brand/')) return route.fulfill({ json: envelope({ name: 'AdminCore', tagline: 'fixture' }) })
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: ['files', 'tasks', 'notifications', 'data_io', 'approvals', 'system', 'organization'].map(key => ({ key, enabled: key !== 'notifications' || state.enabled, paths: key === 'system' ? ['/system/config'] : key === 'data_io' ? [] : [`/${key}`], dependencies: [] })) }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    if (path.endsWith('/notifications/unread_count/')) return route.fulfill({ json: envelope({ count: 0 }) })
    if (path.includes('/announcements/')) {
      if (request.method() === 'GET') {
        if (path.endsWith(`/${state.row.id}/`)) return route.fulfill({ json: envelope({ ...state.row }) })
        return route.fulfill({ json: envelope(paged(path.includes('/manage/') || state.row.status === 'published' ? [{ ...state.row }] : [])) })
      }
      const body = request.postDataJSON() as Record<string, unknown>
      state.writes.push(body)
      if (state.delay) await state.delay
      Object.assign(state.row, body); state.row.version++; state.row.status = 'draft'
      return route.fulfill({ json: envelope({ ...state.row }) })
    }
    if (path.endsWith('/dashboard/stats/')) return route.fulfill({ json: envelope({ totals: {}, login_trend: [], task_status: {} }) })
    return route.fulfill({ json: envelope(paged([])) })
  })
  return state
}

async function manage(page: Page) {
  await page.goto('/notifications/announcements')
  await page.locator('.el-radio-button').filter({ hasText: '公告管理' }).click()
  await expect(page.getByRole('cell', { name: '富文本公告', exact: true })).toBeVisible()
}

async function htmlDraft(page: Page) {
  await page.getByRole('button', { name: '新增公告', exact: true }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: '新增公告' })
  await dialog.getByLabel('标题', { exact: true }).fill('新富文本标题')
  await dialog.locator('.el-radio-button').filter({ hasText: '富文本' }).click()
  const editor = dialog.getByRole('textbox', { name: '公告富文本正文', exact: true })
  await expect(editor).toBeVisible()
  return { dialog, editor }
}

async function paste(editor: Locator, html: string) {
  await editor.focus()
  await editor.evaluate((element, value) => {
    const clipboard = new DataTransfer()
    clipboard.setData('text/html', value)
    clipboard.setData('text/plain', '安全正文')
    element.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: clipboard }))
  }, html)
}

async function assertSafe(region: Locator) {
  await expect(region.locator('img,svg,math,script,style,iframe,object,embed,input,form')).toHaveCount(0)
  expect(await region.evaluate(element => [...(element.firstElementChild?.querySelectorAll('*') || [])].every(node => [...node.attributes].every(attribute =>
    node.tagName === 'A' ? ['href', 'rel'].includes(attribute.name) : false)))).toBe(true)
  const links = region.locator('a[href]')
  for (let index = 0; index < await links.count(); index++) {
    const link = links.nth(index), href = await link.getAttribute('href') || ''
    const url = new URL(href)
    expect(['http:', 'https:']).toContain(url.protocol)
    expect(url.username + url.password).toBe('')
    expect(href).not.toMatch(/[\s\u0000-\u001f\u007f]|%0[09ad]|%7f/i)
    expect((await link.getAttribute('rel') || '').split(' ').sort()).toEqual(['nofollow', 'noopener', 'noreferrer'])
  }
}

test('恶意历史HTML详情二次消毒且不触发脚本或远程图片请求', async ({ page }) => {
  const state = await setup(page, false); state.row.status = 'published'; state.row.content = attack
  const remote: string[] = []
  page.on('request', request => { if (request.url().includes('attacker.invalid')) remote.push(request.url()) })
  await page.goto('/notifications/announcements')
  await page.getByRole('button', { name: '详情', exact: true }).click()
  const region = page.getByRole('region', { name: '公告内容', exact: true })
  await expect(region).toContainText('安全正文')
  await assertSafe(region)
  await expect(region).not.toContainText('discard-')
  expect(await page.evaluate(() => (window as Window & { __richAttack?: number }).__richAttack)).toBeUndefined()
  expect(remote).toEqual([])
})

test('未声明format的旧公告按字面纯文本显示', async ({ page }) => {
  const state = await setup(page, false); state.row.status = 'published'; state.row.content_format = undefined; state.row.content = '<img src=x onerror=alert(1)><strong>旧正文</strong>'
  await page.goto('/notifications/announcements')
  await page.getByRole('button', { name: '详情', exact: true }).click()
  const region = page.getByRole('region', { name: '公告内容', exact: true })
  await expect(region).toContainText(state.row.content)
  await expect(region.locator('img,strong')).toHaveCount(0)
})

test('粘贴攻击经编辑器与预览清洗，保存重开保留安全排版', async ({ page }, testInfo) => {
  const state = await setup(page); await manage(page)
  const { dialog, editor } = await htmlDraft(page)
  await paste(editor, attack + '<p><strong>保留加粗</strong></p>')
  await expect(editor).toContainText('保留加粗')
  await expect(editor.locator('img,script,svg,math,iframe')).toHaveCount(0)
  await dialog.getByRole('button', { name: '预览正文', exact: true }).click()
  const preview = dialog.getByRole('region', { name: '正文预览', exact: true })
  await assertSafe(preview)
  await expect(preview.locator('strong')).toContainText('保留加粗')
  await page.screenshot({ path: testInfo.outputPath('rich-editor.png'), fullPage: true })
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  expect(state.writes).toHaveLength(1)
  expect(state.writes[0]?.content_format).toBe('html')
  expect(String(state.writes[0]?.content)).not.toMatch(/<img|onerror|onclick|discard-|attacker\.invalid/)
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  const reopened = page.getByRole('textbox', { name: '公告富文本正文', exact: true })
  await expect(reopened.locator('strong')).toContainText('保留加粗')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('安全链接设置拒绝凭据与危险协议，预览链接rel完整', async ({ page }) => {
  await setup(page); await manage(page)
  const { dialog, editor } = await htmlDraft(page)
  await editor.fill('链接文字')
  await editor.evaluate(element => {
    const selection = window.getSelection(), range = document.createRange()
    range.selectNodeContents(element); selection?.removeAllRanges(); selection?.addRange(range)
    document.dispatchEvent(new Event('selectionchange'))
  })
  expect(await page.evaluate(() => window.getSelection()?.toString())).toBe('链接文字')
  await dialog.getByRole('button', { name: '设置链接', exact: true }).click()
  for (const value of ['javascript:alert(1)', '//example.test', 'https://user:pass@example.test/', 'https://example.test/a%0ab']) {
    await dialog.getByRole('textbox', { name: '链接地址', exact: true }).fill(value)
    await dialog.getByRole('button', { name: '应用链接', exact: true }).click()
    await expect(dialog.getByRole('alert')).toContainText('链接仅允许')
    await expect(editor.locator('a')).toHaveCount(0)
  }
  await dialog.getByRole('textbox', { name: '链接地址', exact: true }).fill('https://example.test/guide')
  await dialog.getByRole('button', { name: '应用链接', exact: true }).click()
  await dialog.getByRole('button', { name: '预览正文', exact: true }).click()
  const preview = dialog.getByRole('region', { name: '正文预览', exact: true })
  await expect(preview.getByRole('link', { name: '链接文字', exact: true })).toHaveAttribute('href', 'https://example.test/guide')
  await assertSafe(preview)
})

test('新增默认纯文本，切换富文本先确认并转义旧字面HTML', async ({ page }) => {
  const state = await setup(page); await manage(page)
  await page.getByRole('button', { name: '新增公告', exact: true }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: '新增公告' })
  await expect(dialog.getByRole('radio', { name: '纯文本', exact: true })).toBeChecked()
  await dialog.getByLabel('标题', { exact: true }).fill('模式转换')
  const literal = '<img src=x onerror=alert(1)>字面正文'
  await dialog.getByLabel('公告正文', { exact: true }).fill(literal)
  await dialog.locator('.el-radio-button').filter({ hasText: '富文本' }).click()
  const prompt = page.getByRole('dialog').filter({ has: page.getByRole('button', { name: '确定', exact: true }) })
  await prompt.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog.getByLabel('公告正文', { exact: true })).toHaveValue(literal)
  await dialog.locator('.el-radio-button').filter({ hasText: '富文本' }).click()
  await prompt.getByRole('button', { name: '确定', exact: true }).click()
  const editor = dialog.getByRole('textbox', { name: '公告富文本正文', exact: true })
  await expect(editor).toContainText(literal)
  await expect(editor.locator('img')).toHaveCount(0)
  await editor.fill('')
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(dialog.getByRole('alert')).toBeVisible()
  expect(state.writes).toHaveLength(0)
})

test('富文本请求锁定编辑器，撤权后迟到保存不复活草稿', async ({ page }) => {
  const state = await setup(page); await manage(page)
  const { dialog, editor } = await htmlDraft(page)
  await editor.fill('private rich draft')
  let release!: () => void; state.delay = new Promise(resolve => { release = resolve })
  await dialog.getByRole('button', { name: '确认', exact: true }).click()
  await expect(editor).toHaveAttribute('contenteditable', 'false')
  await expect(dialog.getByRole('button', { name: '加粗', exact: true })).toBeDisabled()
  state.admin = false
  const refreshed = page.waitForResponse('**/auth/me/')
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await refreshed
  await expect(dialog).not.toBeVisible()
  release()
  await expect(page.getByRole('textbox', { name: '公告富文本正文', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '新增公告', exact: true })).toHaveCount(0)
  expect(state.writes).toHaveLength(1)
  expect(await page.evaluate(() => Object.values(localStorage).some(value => value.includes('private rich draft')))).toBe(false)
})

test('模块禁用时不加载富文本编辑器也不发送写请求', async ({ page }) => {
  const state = await setup(page); state.enabled = false
  await page.goto('/notifications/announcements')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('textbox', { name: '公告富文本正文', exact: true })).toHaveCount(0)
  expect(state.writes).toHaveLength(0)
})

test('英文暗色工具栏可键盘加粗输入并预览，手机触控目标足够大', async ({ page }, testInfo) => {
  const state = await setup(page)
  await page.addInitScript(() => { localStorage.setItem('language', 'en-US'); localStorage.setItem('theme', 'dark') })
  await page.goto('/notifications/announcements')
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.locator('.el-radio-button').filter({ hasText: 'Manage announcements' }).click()
  await page.getByRole('button', { name: 'New announcement', exact: true }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'New announcement' })
  await dialog.locator('.el-radio-button').filter({ hasText: 'Rich Text' }).click()
  const editor = dialog.getByRole('textbox', { name: 'Announcement Rich Text Body', exact: true })
  const toolbar = dialog.getByRole('toolbar', { name: 'Content Formatting Toolbar', exact: true })
  await expect(editor).toBeVisible()
  const bold = toolbar.getByRole('button', { name: 'Bold', exact: true })
  await bold.focus()
  await page.keyboard.press('Tab')
  await expect(toolbar.getByRole('button', { name: 'Italic', exact: true })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(bold).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(bold).toHaveAttribute('aria-pressed', 'true')
  await expect(editor).toBeFocused()
  await page.keyboard.type('Keyboard bold content')
  await expect(editor.locator('strong')).toHaveText('Keyboard bold content')
  const buttons = toolbar.getByRole('button')
  for (let index = 0; index < await buttons.count(); index++) {
    const box = await buttons.nth(index).boundingBox()
    expect(box?.width).toBeGreaterThanOrEqual(44)
    expect(box?.height).toBeGreaterThanOrEqual(44)
  }
  await dialog.getByRole('button', { name: 'Preview Content', exact: true }).click()
  const preview = dialog.getByRole('region', { name: 'Content Preview', exact: true })
  await expect(preview.locator('strong')).toHaveText('Keyboard bold content')
  await assertSafe(preview)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(state.writes).toHaveLength(0)
  await page.screenshot({ path: testInfo.outputPath('rich-editor-dark-english.png'), fullPage: true })
})
