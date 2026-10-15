import request, { type ApiResponse, type PagedData } from './request'

export interface ConfigRow {
  key: string
  label: string
  kind: 'integer' | 'string' | 'image'
  value: string | number
  default: string | number
  version: number
  minimum: number
  maximum: number
  effective: string
}
export interface DictionaryItem { label: string; value: string; is_active: boolean; order: number }
export interface DictionaryRow {
  id: string
  code: string
  name: string
  description: string
  is_active: boolean
  items: DictionaryItem[]
  version: number
}
export const systemApi = {
  configs: async () => (await request.get<ApiResponse<ConfigRow[]>>('/system/config/')).data.data,
  config: async (key: string, signal?: AbortSignal) => { const rows = (await request.get<ApiResponse<ConfigRow[]>>(`/system/config/${encodeURIComponent(key)}/`, { signal })).data.data; const row = rows.find(item => item.key === key); if (!row) throw new Error('Missing registered config'); return row },
  configUpdate: (row: ConfigRow, value: string | number) => request.patch(`/system/config/${row.key}/`, { value, version: row.version }),
  dictionaries: async (page = 1, search = '', pageSize = 20) => (await request.get<ApiResponse<PagedData<DictionaryRow>>>('/system/dictionaries/', { params: { page, page_size: pageSize, search } })).data.data,
  dictionary: async (id: string, signal?: AbortSignal) => (await request.get<ApiResponse<DictionaryRow>>(`/system/dictionaries/${id}/`, { signal })).data.data,
  createDictionary: (data: Omit<DictionaryRow, 'id'>) => request.post('/system/dictionaries/', data),
  updateDictionary: (id: string, data: Omit<DictionaryRow, 'id'>) => request.patch(`/system/dictionaries/${id}/`, data),
  options: async (code: string) => (await request.get<ApiResponse<{ code: string; version: number; items: DictionaryItem[] }>>(`/system/dictionaries/options/${encodeURIComponent(code)}/`)).data.data,
}
