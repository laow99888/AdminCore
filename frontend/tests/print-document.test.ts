import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ElButton } from 'element-plus'
import { i18n } from '../src/i18n'
import PrintTableButton from '../src/components/common/PrintTableButton.vue'
import { buildPrintDocument, openPrintDocument, PrintDocumentError, type PrintColumn, type PrintCell } from '../src/utils/printDocument'

type Row = { name: string; secret?: string }
const columns: PrintColumn<Row>[] = [{ label: '用户名', value: row => row.name }]
const options = { title: '用户列表', rows: [{ name: '成员中文', secret: 'never-print-this' }], columns, currentPage: 3, generatedAt: new Date('2026-10-14T08:00:00Z') }
function fakePopup() {
  const target = new EventTarget()
  const fakeDocument = { open: vi.fn(), write: vi.fn(), close: vi.fn() }
  const popup = Object.assign(target, { opener: {} as unknown, document: fakeDocument, closed: false, close: vi.fn(), focus: vi.fn(), print: vi.fn() })
  const open = vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window)
  return { popup, open, fakeDocument }
}

describe('白名单静态打印文档', () => {
  beforeEach(() => { vi.useFakeTimers(); i18n.global.locale.value = 'zh-CN' })
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

  it('只输出当前传入页及选定字段，包含中文、页号、数量、时间与保存 PDF 提示', () => {
    const document = new DOMParser().parseFromString(buildPrintDocument(options), 'text/html')
    expect(document.documentElement.lang).toBe('zh-CN')
    expect(document.querySelectorAll('tbody tr')).toHaveLength(1)
    expect(document.body.textContent).toContain('当前第 3 页 · 1 条记录')
    expect(document.body.textContent).toContain('成员中文')
    expect(document.body.textContent).toContain('2026')
    expect(document.body.textContent).toContain('另存为 PDF')
    expect(document.body.textContent).not.toContain('never-print-this')
    expect(document.querySelector('th')?.getAttribute('scope')).toBe('col')
  })

  it('标题、列名与单元格全部转义；脚本、事件和脚本 URL 只能作为原始文字', () => {
    const unsafe = '</title><script>globalThis.pwned=true</script><img src=x onerror=alert(1)> & " \' javascript:alert(1)'
    const document = new DOMParser().parseFromString(buildPrintDocument({ ...options, title: unsafe, rows: [{ name: unsafe }], columns: [{ label: unsafe, value: row => row.name }] }), 'text/html')
    expect(document.title).toBe(unsafe)
    expect(document.querySelector('th')?.textContent).toBe(unsafe)
    expect(document.querySelector('td')?.textContent).toBe(unsafe)
    expect(document.querySelectorAll('script,img,a,iframe,form')).toHaveLength(0)
    expect(document.querySelector('meta[http-equiv="Content-Security-Policy"]')?.getAttribute('content')).toContain("script-src 'none'")
  })

  it('英文、空态和多行文本适配，分页表头、换行和白底不依赖应用主题', () => {
    const empty = new DOMParser().parseFromString(buildPrintDocument({ ...options, locale: 'en-US', rows: [] }), 'text/html')
    expect(empty.documentElement.lang).toBe('en-US')
    expect(empty.body.textContent).toContain('Current page 3 · 0 records')
    expect(empty.body.textContent).toContain('No records on this page')
    expect(empty.body.textContent).toContain('Save as PDF')
    const html = buildPrintDocument({ ...options, rows: [{ name: '第一行\n第二行' }] })
    expect(html).toContain('第一行\n第二行')
    expect(html).toContain('table-header-group')
    expect(html).toContain('white-space:pre-wrap')
    expect(html).toContain('color-scheme:light;background:#fff')
  })

  it('日期单元格按语言格式化，空值留空，布尔与数字保留', () => {
    const html = buildPrintDocument({ ...options, columns: [new Date('2026-10-14T08:00:00Z'), null, undefined, false, 0].map(value => ({ label: '值', value: () => value })) })
    const document = new DOMParser().parseFromString(html, 'text/html')
    expect([...document.querySelectorAll('td')].map(cell => cell.textContent)).toEqual([expect.stringContaining('2026'), '', '', 'false', '0'])
  })

  it.each([{}, [], () => 'secret', Infinity, NaN, 'x'.repeat(10001)])('拒绝不支持的值或超长文本，不把对象序列化泄露字段 %#', value => {
    expect(() => buildPrintDocument({ ...options, columns: [{ label: '值', value: () => value as PrintCell }] })).toThrow(PrintDocumentError)
  })

  it('行、列、全文超限直接拒绝，不静默截断', () => {
    expect(() => buildPrintDocument({ ...options, rows: Array.from({ length: 101 }, () => ({ name: 'row' })) })).toThrow(PrintDocumentError)
    expect(() => buildPrintDocument({ ...options, columns: [] })).toThrow(PrintDocumentError)
    expect(() => buildPrintDocument({ ...options, columns: Array.from({ length: 21 }, () => columns[0]!) })).toThrow(PrintDocumentError)
    expect(() => buildPrintDocument({ ...options, rows: Array.from({ length: 100 }, () => ({ name: 'x'.repeat(10000) })) })).toThrow(PrintDocumentError)
  })

  it('写文档之前隔离 opener；父页触发打印，结束时关闭并移除计时器', () => {
    const { popup, fakeDocument } = fakePopup()
    fakeDocument.write.mockImplementation(() => expect(popup.opener).toBeNull())
    const onEnd = vi.fn(), onError = vi.fn()
    const session = openPrintDocument(options, { allowed: () => true, onEnd, onError })
    expect(fakeDocument.write).toHaveBeenCalledOnce()
    expect(popup.print).not.toHaveBeenCalled()
    vi.advanceTimersByTime(0)
    expect(popup.print).toHaveBeenCalledOnce()
    popup.dispatchEvent(new Event('afterprint'))
    session.dispose()
    expect(popup.close).toHaveBeenCalledOnce()
    expect(onEnd).toHaveBeenCalledOnce()
    expect(onError).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('弹窗阻止、权限不足与创建失败不遗留窗口或计时器，可由调用方重试', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    expect(() => openPrintDocument(options, { allowed: () => true, onEnd: vi.fn(), onError: vi.fn() })).toThrow(expect.objectContaining({ reason: 'blocked' }))
    expect(() => openPrintDocument(options, { allowed: () => false, onEnd: vi.fn(), onError: vi.fn() })).toThrow(PrintDocumentError)
    expect(open).toHaveBeenCalledOnce()
    const { popup, fakeDocument } = fakePopup()
    fakeDocument.write.mockImplementation(() => { throw new Error('denied') })
    expect(() => openPrintDocument(options, { allowed: () => true, onEnd: vi.fn(), onError: vi.fn() })).toThrow(PrintDocumentError)
    expect(popup.close).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('打印前失权、手动关闭、父页离开和打印异常均停止并清理', () => {
    for (const mode of ['revoke', 'closed', 'unload', 'error']) {
      const { popup } = fakePopup()
      let allowed = true
      const onEnd = vi.fn(), onError = vi.fn()
      openPrintDocument(options, { allowed: () => allowed, onEnd, onError })
      if (mode === 'revoke') allowed = false
      if (mode === 'closed') popup.closed = true
      if (mode === 'unload') window.dispatchEvent(new Event('beforeunload'))
      if (mode === 'error') popup.print.mockImplementation(() => { throw new Error('unsupported') })
      vi.advanceTimersByTime(500)
      expect(onEnd).toHaveBeenCalledOnce()
      expect(popup.close).toHaveBeenCalledOnce()
      expect(vi.getTimerCount()).toBe(0)
      expect(onError).toHaveBeenCalledTimes(mode === 'error' ? 1 : 0)
    }
  })

  it('窗口被外部导航后不读取或关闭替换文档，也不继续打印', () => {
    const { popup } = fakePopup()
    const onEnd = vi.fn()
    const session = openPrintDocument(options, { allowed: () => true, onEnd, onError: vi.fn() })
    popup.document = { open: vi.fn(), write: vi.fn(), close: vi.fn() }
    vi.advanceTimersByTime(0)
    session.dispose()
    expect(popup.close).not.toHaveBeenCalled()
    expect(popup.print).not.toHaveBeenCalled()
    expect(onEnd).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('外部跨域导航拒绝 document 读取时结束本次会话，不关闭其他文档', () => {
    const { popup } = fakePopup()
    const onEnd = vi.fn()
    openPrintDocument(options, { allowed: () => true, onEnd, onError: vi.fn() })
    vi.advanceTimersByTime(0)
    Object.defineProperty(popup, 'document', { get() { throw new DOMException('cross-origin', 'SecurityError') } })
    vi.advanceTimersByTime(500)
    expect(popup.close).not.toHaveBeenCalled()
    expect(onEnd).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('组件默认无权限不显示；空态和加载禁用；重复点击只产生一个窗口', async () => {
    const { open } = fakePopup()
    const wrapper = mount(PrintTableButton<Row>, { props: { ...options, allowed: false }, global: { plugins: [i18n], components: { ElButton } } })
    expect(wrapper.find('button').exists()).toBe(false)
    await wrapper.setProps({ allowed: true, rows: [] })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ rows: options.rows, loading: true })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ loading: false })
    await wrapper.get('button').trigger('click')
    await wrapper.get('button').trigger('click')
    expect(open).toHaveBeenCalledOnce()
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('组件 owner、权限、数据页变化与卸载关闭打印窗口，恢复后可重试', async () => {
    const { open, popup } = fakePopup()
    const wrapper = mount(PrintTableButton<Row>, { props: { ...options, allowed: true, ownerKey: 'owner-a' }, global: { plugins: [i18n], components: { ElButton } } })
    await wrapper.get('button').trigger('click')
    await wrapper.setProps({ ownerKey: 'owner-b' })
    expect(popup.close).toHaveBeenCalledTimes(1)
    await wrapper.get('button').trigger('click')
    await wrapper.setProps({ currentPage: 4 })
    expect(popup.close).toHaveBeenCalledTimes(2)
    await wrapper.get('button').trigger('click')
    await wrapper.setProps({ allowed: false })
    expect(popup.close).toHaveBeenCalledTimes(3)
    expect(wrapper.find('button').exists()).toBe(false)
    await wrapper.setProps({ allowed: true })
    await wrapper.get('button').trigger('click')
    wrapper.unmount()
    expect(open).toHaveBeenCalledTimes(4)
    expect(popup.close).toHaveBeenCalledTimes(4)
    expect(vi.getTimerCount()).toBe(0)
  })
})
