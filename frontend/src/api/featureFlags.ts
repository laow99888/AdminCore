import request, { type ApiResponse, type PagedData } from './request'

export interface FeatureFlagWrite {
  key: string
  name: string
  description: string
  enabled: boolean
  rollout: number
  included_users: string[]
  excluded_users: string[]
  roles: string[]
  version: number
}
export interface FeatureFlag extends FeatureFlagWrite { id: string; created_at: string; updated_at: string }
export interface FlagTarget { id: string; label: string }
export const featureFlagsApi = {
  async list(params: { page: number; page_size: number; search: string }, signal?: AbortSignal) {
    return (await request.get<ApiResponse<PagedData<FeatureFlag>>>('/feature-flags/flags/', { params, signal })).data.data
  },
  async detail(id: string, signal?: AbortSignal) {
    return (await request.get<ApiResponse<FeatureFlag>>(`/feature-flags/flags/${id}/`, { signal })).data.data
  },
  async save(id: string, data: FeatureFlagWrite, key: string) {
    return id ? request.patch(`/feature-flags/flags/${id}/`, data) : request.post('/feature-flags/flags/', data, { headers: { 'Idempotency-Key': key } })
  },
  async remove(id: string, version: number) { return request.delete(`/feature-flags/flags/${id}/`, { data: { version } }) },
  async targets(kind: 'users' | 'roles', search: string, selected: string[], signal?: AbortSignal) {
    return (await request.get<ApiResponse<FlagTarget[]>>('/feature-flags/targets/', { params: { kind, search, selected: selected.join(',') }, signal })).data.data
  },
  async evaluate(keys: string[], signal?: AbortSignal) {
    return (await request.post<ApiResponse<Array<{ key: string; enabled: boolean }>>>('/feature-flags/evaluate/', { keys }, { signal })).data.data
  },
}
