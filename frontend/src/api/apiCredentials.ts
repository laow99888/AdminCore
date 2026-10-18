import request, { type ApiResponse, type PagedData } from './request'

export interface APICredential {
  id: string
  name: string
  scopes: string[]
  created_at: string
  expires_at: string
  revoked_at: string | null
  last_used_at: string | null
  version: number
  rotated_at: string | null
  accepted_requests: number
  statistics_started_at: string
}
export interface CredentialStatistics { days: number; timezone: string; statistics_started_at: string; accepted_requests: number; recent_requests: number; daily: { day: string; requests: number }[] }
export interface CredentialDraft { name: string; scopes: string[]; expires_at: string }
export const apiCredentialsApi = {
  list: async (page: number, pageSize: number, signal?: AbortSignal) =>
    (await request.get<ApiResponse<PagedData<APICredential>>>('/api-credentials/credentials/', { params: { page, page_size: pageSize }, signal })).data.data,
  scopes: async (signal?: AbortSignal) =>
    (await request.get<ApiResponse<{ code: string; label: string }[]>>('/api-credentials/credentials/scopes/', { signal })).data.data,
  create: async (draft: CredentialDraft, currentPassword: string) =>
    (await request.post<ApiResponse<APICredential & { token: string }>>('/api-credentials/credentials/', { ...draft, current_password: currentPassword })).data.data,
  revoke: async (id: string, currentPassword: string) =>
    (await request.post<ApiResponse<null>>(`/api-credentials/credentials/${encodeURIComponent(id)}/revoke/`, { current_password: currentPassword })).data.data,
  rotate: async (id: string, version: number, currentPassword: string) =>
    (await request.post<ApiResponse<APICredential & { token: string }>>(`/api-credentials/credentials/${encodeURIComponent(id)}/rotate/`, { version, current_password: currentPassword })).data.data,
  statistics: async (id: string, days = 7, signal?: AbortSignal) =>
    (await request.get<ApiResponse<CredentialStatistics>>(`/api-credentials/credentials/${encodeURIComponent(id)}/statistics/`, { params: { days }, signal })).data.data,
}
