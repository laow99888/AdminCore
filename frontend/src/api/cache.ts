import request, { type ApiResponse } from './request'

export type CacheNamespace = 'configuration' | 'dictionaries'
export type CacheBackend = 'shared' | 'in_process' | 'unsupported'
export interface CacheCatalog {
  backend: CacheBackend
  limit: number
  ttl_seconds: number
  namespaces: { namespace: CacheNamespace; module: string; candidate_count: number; over_limit: boolean }[]
}
export interface CachePreview { namespace: CacheNamespace; candidate_count: number; backend: CacheBackend; token: string; expires_in: number }
export const cacheApi = {
  catalog: async () => (await request.get<ApiResponse<CacheCatalog>>('/system/cache/')).data.data,
  preview: async (namespace: CacheNamespace) => (await request.post<ApiResponse<CachePreview>>('/system/cache/preview/', { namespace })).data.data,
  clear: async (preview: CachePreview) => (await request.post<ApiResponse<{ outcome: 'completed' }>>('/system/cache/clear/', { namespace: preview.namespace, token: preview.token })).data.data,
}
