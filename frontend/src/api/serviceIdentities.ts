import request, { type ApiResponse, type PagedData } from './request'
import type { APICredential, CredentialDraft } from './apiCredentials'
export interface ServiceIdentity { id: string; name: string; description: string; tenant_id: string | null; is_active: boolean; role_ids: string[]; version: number; created_at: string }
export interface IdentityDraft { name: string; description: string; role_ids: string[] }
const base = '/api-credentials/service-identities/'
const target = (id: string) => `${base}${encodeURIComponent(id)}/`
export const serviceIdentitiesApi = {
  list: async (page: number, pageSize = 10, signal?: AbortSignal) => (await request.get<ApiResponse<PagedData<ServiceIdentity>>>(base, { params: { page, page_size: pageSize }, signal })).data.data,
  roles: async (signal?: AbortSignal) => (await request.get<ApiResponse<{ id: string; name: string }[]>>(`${base}roles/`, { signal })).data.data,
  create: async (draft: IdentityDraft, password: string) => (await request.post<ApiResponse<ServiceIdentity>>(base, { ...draft, current_password: password })).data.data,
  update: async (row: ServiceIdentity, changes: Partial<IdentityDraft> & { is_active?: boolean }, password: string) => (await request.patch<ApiResponse<ServiceIdentity>>(target(row.id), { ...changes, version: row.version, current_password: password })).data.data,
  credentials: async (id: string, signal?: AbortSignal) => (await request.get<ApiResponse<APICredential[]>>(`${target(id)}credentials/`, { signal })).data.data,
  issue: async (id: string, draft: CredentialDraft, password: string) => (await request.post<ApiResponse<APICredential & { token: string }>>(`${target(id)}issue/`, { ...draft, current_password: password })).data.data,
  rotate: async (id: string, credential: APICredential, password: string) => (await request.post<ApiResponse<APICredential & { token: string }>>(`${target(id)}rotate/`, { credential_id: credential.id, version: credential.version, current_password: password })).data.data,
  revoke: async (id: string, credential: APICredential, password: string) => (await request.post<ApiResponse<APICredential>>(`${target(id)}revoke/`, { credential_id: credential.id, version: credential.version, current_password: password })).data.data,
}
