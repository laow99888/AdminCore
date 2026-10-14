import type { PrintCell, PrintColumn } from './printDocument'

export const LOCAL_EXPORT_LIMITS = { rows: 100, columns: 20, cell: 10000, text: 1000000, bytes: 10 * 1024 * 1024 } as const
export interface LocalWorkbookSnapshot {
  title: string
  headers: string[]
  rows: string[][]
  currentPage: number
  locale: 'zh-CN' | 'en-US'
  generatedAt: string
}
export class LocalWorkbookError extends Error {
  constructor() { super('invalid-local-workbook') }
}
// Excel 文本上限、XML 非法控制符与孤立代理项不静默截断或修复。
function cellText(value: PrintCell): string {
  const result = value == null ? '' : value instanceof Date ? (Number.isFinite(value.getTime()) ? value.toISOString() : null)
    : typeof value === 'string' || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value)) ? String(value) : null
  if (result === null || result.length > LOCAL_EXPORT_LIMITS.cell || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]|[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/u.test(result)) throw new LocalWorkbookError()
  return result
}

export function validateWorkbookSnapshot(value: unknown): asserts value is LocalWorkbookSnapshot {
  if (!value || typeof value !== 'object') throw new LocalWorkbookError()
  const data = value as LocalWorkbookSnapshot
  if (typeof data.title !== 'string' || data.title.length > 100 || !Array.isArray(data.headers) || data.headers.length < 1 || data.headers.length > LOCAL_EXPORT_LIMITS.columns ||
      !Array.isArray(data.rows) || data.rows.length < 1 || data.rows.length > LOCAL_EXPORT_LIMITS.rows || !Number.isSafeInteger(data.currentPage) || data.currentPage < 1 ||
      !['zh-CN', 'en-US'].includes(data.locale) || typeof data.generatedAt !== 'string' || data.generatedAt.length > 30 || !Number.isFinite(Date.parse(data.generatedAt))) throw new LocalWorkbookError()
  let characters = cellText(data.title).length + data.generatedAt.length
  for (const row of [data.headers, ...data.rows]) {
    if (!Array.isArray(row) || row.length !== data.headers.length) throw new LocalWorkbookError()
    for (const cell of row) {
      if (typeof cell !== 'string') throw new LocalWorkbookError()
      characters += cellText(cell).length
      if (characters > LOCAL_EXPORT_LIMITS.text) throw new LocalWorkbookError()
    }
  }
}

/** 只投影调用方登记的列。完整行、DOM、临时敏感值和筛选表单不会发送到 Worker。 */
export function snapshotWorkbook<T>(options: { title: string; rows: readonly T[]; columns: readonly PrintColumn<T>[]; currentPage: number; locale: string }): LocalWorkbookSnapshot {
  if (options.rows.length > LOCAL_EXPORT_LIMITS.rows || options.columns.length > LOCAL_EXPORT_LIMITS.columns) throw new LocalWorkbookError()
  const result: LocalWorkbookSnapshot = {
    title: options.title,
    headers: options.columns.map(column => cellText(column.label)),
    rows: options.rows.map(row => options.columns.map(column => cellText(column.value(row)))),
    currentPage: options.currentPage,
    locale: options.locale === 'en-US' ? 'en-US' : 'zh-CN',
    generatedAt: new Date().toISOString(),
  }
  validateWorkbookSnapshot(result)
  return result
}
