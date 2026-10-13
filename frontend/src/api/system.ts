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
  configUpdate: (row: ConfigRow, value: string | number) => request.patch(`/system/config/${row.key}/`, { value, version: row.version }),
  dictionaries: async (page = 1, search = '', pageSize = 20) => (await request.get<ApiResponse<PagedData<DictionaryRow>>>('/system/dictionaries/', { params: { page, page_size: pageSize, search } })).data.data,
  createDictionary: (data: Omit<DictionaryRow, 'id'>) => request.post('/system/dictionaries/', data),
  updateDictionary: (id: string, data: Omit<DictionaryRow, 'id'>) => request.patch(`/system/dictionaries/${id}/`, data),
  options: async (code: string) => (await request.get<ApiResponse<{ code: string; version: number; items: DictionaryItem[] }>>(`/system/dictionaries/options/${encodeURIComponent(code)}/`)).data.data,
}
