export type ScalarValue = string | number | boolean | null | undefined
export type DetailRow = { display_labels?: Record<string, string>; [key: string]: unknown }
export type GeneratedRecord = DetailRow & { id: string; version: number; approval_status?: string }

export function scalarValue(value: unknown): ScalarValue {
  return value == null || ['string', 'number', 'boolean'].includes(typeof value) ? value as ScalarValue : undefined
}

/** API 和草稿均只接受对象明细行；标量不能成为动态输入模型。 */
export function detailRows(record: DetailRow, name: string): DetailRow[] {
  const rows = record[name]
  return Array.isArray(rows) && rows.every(row => row && typeof row === 'object' && !Array.isArray(row)) ? rows : []
}
