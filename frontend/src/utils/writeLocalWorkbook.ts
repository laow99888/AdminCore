import { utils, write, type CellObject } from 'xlsx'
import { LOCAL_EXPORT_LIMITS, LocalWorkbookError, validateWorkbookSnapshot } from './localWorkbook'

/** 库只在专用 Worker 中加载；不读取文件，不写公式、链接、宏或外部关系。 */
export function writeLocalWorkbook(snapshot: unknown): ArrayBuffer {
  validateWorkbookSnapshot(snapshot)
  const workbook = utils.book_new()
  const text = (rows: string[][]) => utils.aoa_to_sheet(rows.map(row => row.map(value => ({ t: 's', v: value, z: '@' } as CellObject))))
  utils.book_append_sheet(workbook, text([snapshot.headers, ...snapshot.rows]), 'Data')
  const english = snapshot.locale === 'en-US'
  utils.book_append_sheet(workbook, text([
    [english ? 'Title' : '标题', snapshot.title],
    [english ? 'Current page' : '当前页', String(snapshot.currentPage)],
    [english ? 'Records' : '记录数', String(snapshot.rows.length)],
    [english ? 'Generated at (UTC)' : '生成时间（UTC）', snapshot.generatedAt],
    [english ? 'Scope' : '范围', english ? 'Only the currently loaded page and declared columns. No additional records were requested.' : '仅包含当前已加载页的白名单字段，没有请求其他记录。'],
  ]), 'Export info')
  workbook.Props = { Title: snapshot.title, Author: 'AdminCore', CreatedDate: new Date(snapshot.generatedAt) }
  const bytes: unknown = write(workbook, { type: 'array', bookType: 'xlsx', compression: true, bookSST: false })
  if (!(bytes instanceof ArrayBuffer) || !bytes.byteLength || bytes.byteLength > LOCAL_EXPORT_LIMITS.bytes) throw new LocalWorkbookError()
  return bytes
}
