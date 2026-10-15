import request, { type ApiResponse, type PagedData } from './request'

export interface APICredential {
  id: string
  name: string
  scopes: string[]
  created_at: string
  expires_at: string
  revoked_at: string | null
  last_used_at: string | null
}
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
}
