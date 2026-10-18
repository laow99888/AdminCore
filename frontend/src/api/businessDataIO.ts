import request, { type ApiResponse } from './request'

const root = '/data-io/business/'
export interface MappingOptions { mapping: Record<string, string>; key: string; mode: string }
export interface ImportField { name: string; label: string; required: boolean; key: boolean }
export interface ImportCatalog { fields: ImportField[]; modes: string[]; max_rows: number; max_bytes: number; structure?: string; exportable?: boolean }
export interface ImportSummary { total: number; created: number; updated: number; skipped: number; failed: number; processed?: number; source_rows?: number }
export interface ImportPreview { id: string; summary: ImportSummary; expires_at: string; errors: Array<{ row: number; message: string }> }
export interface PersonalMapping { id: string; name: string; options: MappingOptions }
export interface BusinessTask { id: string; status: string; progress: number; result: Partial<ImportSummary>; error_message?: string }
export interface BusinessExportTask { id: string; status: string; progress: number; result: { documents?: number; rows?: number; expires_at?: string }; error?: string }
async function get<T>(path: string, params: Record<string, string>, signal?: AbortSignal) {
  return (await request.get<ApiResponse<T>>(root + path, { params, signal })).data.data
}
function upload(resource: string, file: File, options?: MappingOptions) {
  const body = new FormData(); body.append('resource', resource); body.append('file', file)
  if (options) body.append('options', JSON.stringify(options))
  return body
}
export const businessDataIO = {
  startExport: async (resource: string, format: 'csv' | 'xlsx', filters: Record<string, string>, signal?: AbortSignal) =>
    (await request.post<ApiResponse<BusinessExportTask>>(root + 'exports/', { resource, format, filters }, { signal })).data.data,
  exportTask: async (id: string, signal?: AbortSignal) =>
    (await request.get<ApiResponse<BusinessExportTask>>(root + `exports/${id}/`, { signal })).data.data,
  exportDownload: async (id: string, signal?: AbortSignal) =>
    (await request.get<Blob>(root + `exports/${id}/download/`, { responseType: 'blob', signal })).data,
  catalog: (resource: string, signal?: AbortSignal) => get<ImportCatalog>('catalog/', { resource }, signal),
  inspect: async (resource: string, file: File, signal?: AbortSignal) =>
    (await request.post<ApiResponse<{ headers: string[]; rows: number }>>(root + 'inspect/', upload(resource, file), { signal })).data.data,
  preview: async (resource: string, file: File, options: MappingOptions, signal?: AbortSignal) =>
    (await request.post<ApiResponse<ImportPreview>>(root + 'preview/', upload(resource, file, options), { signal })).data.data,
  submit: async (id: string, signal?: AbortSignal) =>
    (await request.post<ApiResponse<BusinessTask>>(root + `plans/${id}/submit/`, undefined, { signal })).data.data,
  task: async (id: string, signal?: AbortSignal) =>
    (await request.get<ApiResponse<BusinessTask>>(`/data-io/import/${id}/`, { signal })).data.data,
  mappings: (resource: string, signal?: AbortSignal) => get<PersonalMapping[]>('mappings/', { resource }, signal),
  save: async (resource: string, name: string, options: MappingOptions, signal?: AbortSignal) =>
    (await request.post<ApiResponse<PersonalMapping>>(root + 'mappings/', { resource, name, options }, { signal })).data.data,
  remove: (id: string, signal?: AbortSignal) => request.delete(root + `mappings/${id}/`, { signal }),
  errors: async (id: string, signal?: AbortSignal) =>
    (await request.get<Blob>(root + `import/${id}/errors/`, { responseType: 'blob', signal })).data,
  previewErrors: async (id: string, signal?: AbortSignal) =>
    (await request.get<Blob>(root + `plans/${id}/errors/`, { responseType: 'blob', signal })).data,
  export: async (resource: string, format: 'csv' | 'xlsx', filters: Record<string, string>, signal?: AbortSignal) =>
    (await request.get<Blob>(root + 'export/', { params: { ...filters, resource, export_format: format }, responseType: 'blob', signal })).data,
}
