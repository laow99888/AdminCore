/** 打印只接收调用方明确选择的当前页文本列，不读取 DOM、链接或完整对象。 */
export type PrintCell = string | number | boolean | Date | null | undefined
export interface PrintColumn<T> {
  label: string
  value: (row: T) => PrintCell
}
export interface PrintDocumentOptions<T> {
  title: string
  rows: readonly T[]
  columns: readonly PrintColumn<T>[]
  locale?: 'zh-CN' | 'en-US'
  currentPage?: number
  generatedAt?: Date
}
export type PrintFailure = 'blocked' | 'invalid' | 'failed'
export class PrintDocumentError extends Error {
  constructor(public readonly reason: PrintFailure) { super(reason) }
}

const MAX_ROWS = 100
const MAX_COLUMNS = 20
const MAX_CELL_LENGTH = 10000
const MAX_DOCUMENT_LENGTH = 1000000

export function escapePrintText(value: string): string {
  return value.replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!)
}

function text(value: PrintCell, locale: 'zh-CN' | 'en-US'): string {
  if (value == null) return ''
  const result = value instanceof Date ? (Number.isFinite(value.getTime()) ? new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(value) : '')
    : typeof value === 'string' || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value)) ? String(value) : null
  if (result === null || result.length > MAX_CELL_LENGTH) throw new PrintDocumentError('invalid')
  return escapePrintText(result)
}

export function buildPrintDocument<T>(options: PrintDocumentOptions<T>): string {
  const locale = options.locale === 'en-US' ? 'en-US' : 'zh-CN'
  if (options.rows.length > MAX_ROWS || options.columns.length === 0 || options.columns.length > MAX_COLUMNS) throw new PrintDocumentError('invalid')
  const title = text(options.title, locale)
  const page = Number.isSafeInteger(options.currentPage) && options.currentPage! > 0 ? options.currentPage! : 1
  const summary = locale === 'en-US' ? `Current page ${page} · ${options.rows.length} records` : `当前第 ${page} 页 · ${options.rows.length} 条记录`
  const generated = locale === 'en-US' ? 'Generated at' : '生成时间'
  const note = locale === 'en-US' ? 'Only the currently loaded page is included. Choose Save as PDF in the browser print dialog.' : '仅包含当前已加载页。在浏览器打印窗口中选择“另存为 PDF”。'
  const headers = options.columns.map(column => `<th scope="col">${text(column.label, locale)}</th>`).join('')
  const rows = options.rows.map(row => `<tr>${options.columns.map(column => `<td>${text(column.value(row), locale)}</td>`).join('')}</tr>`).join('')
  const empty = locale === 'en-US' ? 'No records on this page' : '当前页暂无数据'
  const document = `<!doctype html><html lang="${locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'"><title>${title}</title><style>
@page{size:A4; margin:14mm}*{box-sizing:border-box}html{color-scheme:light;background:#fff;color:#111}body{margin:24px;font:14px/1.5 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}h1{font-size:22px;margin:0 0 8px;overflow-wrap:anywhere}.metadata,.note{margin:6px 0;color:#444;font-size:12px}table{width:100%;border-collapse:collapse;table-layout:fixed;margin-top:18px}th,td{border:1px solid #aaa;padding:8px;text-align:left;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}th{font-weight:600;background:#f3f4f6}thead{display:table-header-group}tr{break-inside:avoid}.empty{text-align:center;color:#555}@media(max-width:600px){body{margin:12px}th,td{padding:5px;font-size:12px}}@media print{body{margin:0}h1{break-after:avoid}table{font-size:11px}th,td{padding:6px}.note{font-size:10px}}
</style></head><body><h1>${title}</h1><p class="metadata">${summary}</p><p class="metadata">${generated}: ${text(options.generatedAt ?? new Date(), locale)}</p><p class="note">${note}</p><table><thead><tr>${headers}</tr></thead><tbody>${rows || `<tr><td class="empty" colspan="${options.columns.length}">${empty}</td></tr>`}</tbody></table></body></html>`
  if (document.length > MAX_DOCUMENT_LENGTH) throw new PrintDocumentError('invalid')
  return document
}

export interface PrintSession { dispose: () => void }

/** 先隔离 opener，再写入静态文档。保留 handle 仅用于结束打印或权限变更时关闭自建窗口。 */
export function openPrintDocument<T>(options: PrintDocumentOptions<T>, lifecycle: {
  allowed: () => boolean
  onEnd: () => void
  onError: (reason: PrintFailure) => void
}, host: Window = window): PrintSession {
  if (!lifecycle.allowed()) throw new PrintDocumentError('failed')
  const html = buildPrintDocument(options)
  const popup = host.open('', '_blank')
  if (!popup) throw new PrintDocumentError('blocked')
  let ended = false
  let ownedDocument: Document | undefined
  let printTimer: number | undefined
  let closeTimer: number | undefined
  const dispose = () => {
    if (ended) return
    ended = true
    if (printTimer !== undefined) host.clearTimeout(printTimer)
    if (closeTimer !== undefined) host.clearInterval(closeTimer)
    host.removeEventListener('beforeunload', dispose)
    try {
      if (!ownedDocument || popup.document === ownedDocument) { popup.removeEventListener('afterprint', dispose); popup.close() }
    } catch { /* 外部导航后不读取或关闭其他文档。 */ }
    lifecycle.onEnd()
  }
  try {
    popup.opener = null
    if (popup.opener !== null) throw new PrintDocumentError('failed')
    popup.document.open()
    popup.document.write(html)
    popup.document.close()
    ownedDocument = popup.document
    popup.addEventListener('afterprint', dispose)
    host.addEventListener('beforeunload', dispose)
    closeTimer = host.setInterval(() => {
      try { if (popup.closed || popup.document !== ownedDocument) dispose() }
      catch { dispose() }
    }, 500)
    printTimer = host.setTimeout(() => {
      if (ended) return
      if (!lifecycle.allowed() || popup.closed) { dispose(); return }
      try {
        if (popup.document !== ownedDocument) { dispose(); return }
        popup.focus(); popup.print()
      } catch { dispose(); lifecycle.onError('failed') }
    }, 0)
  } catch {
    dispose()
    throw new PrintDocumentError('failed')
  }
  return { dispose }
}
