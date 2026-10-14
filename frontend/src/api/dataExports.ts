import request from './request'

export type ExportResource = 'users' | 'roles' | 'logs' | 'files'
export type ExportFormat = 'csv' | 'xlsx'
export type ExportFilters = Record<string, string | boolean | null | undefined>

export async function exportData(resource: ExportResource, format: ExportFormat, filters: ExportFilters, signal?: AbortSignal) {
  const params: Record<string, string | boolean> = { resource, export_format: format }
  for (const [key, value] of Object.entries(filters)) {
    if (key === 'resource' || key === 'export_format') throw new Error('非法导出筛选参数')
    if (value !== undefined && value !== null && value !== '') params[key] = value
  }
  const response = await request.get<Blob>('/data-io/export/', { params, responseType: 'blob', signal })
  return response.data
}

export async function exportErrorMessage(error: unknown): Promise<string | undefined> {
  const body = (error as { response?: { data?: unknown } })?.response?.data
  try {
    const data = body instanceof Blob ? JSON.parse(await body.text()) : body
    if (data && typeof (data as { message?: unknown }).message === 'string') return (data as { message: string }).message
  } catch { /* 非 JSON 错误不显示服务器内容，使用通用可重试提示。 */ }
}
