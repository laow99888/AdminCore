import request, { type ApiResponse, type PagedData } from './request'

export interface DeviceSession {
  id: string
  created_at: string
  last_seen_at: string
  expires_at: string
  ip_address: string | null
  user_agent: string
  is_current: boolean
  active: boolean
}
export interface OnlineUser {
  id: string
  username: string
  first_name: string
  last_name: string
  session_count: number
  last_seen_at: string
  is_current_user: boolean
}
export const sessionsApi = {
  list: async (page: number, pageSize: number, signal?: AbortSignal) =>
    (await request.get<ApiResponse<PagedData<DeviceSession>>>('/auth/sessions/', { params: { page, page_size: pageSize }, signal })).data.data,
  onlineUsers: async (page: number, pageSize: number, search: string, signal?: AbortSignal) =>
    (await request.get<ApiResponse<PagedData<OnlineUser>>>('/auth/online-users/', { params: { page, page_size: pageSize, search }, signal })).data.data,
  revoke: async (id: string, currentPassword: string) =>
    (await request.delete<ApiResponse<{ revoked_count: number }>>(`/auth/sessions/${encodeURIComponent(id)}/`, { data: { current_password: currentPassword } })).data.data,
  revokeAll: async (id: string, currentPassword: string) =>
    (await request.post<ApiResponse<{ revoked_count: number }>>(`/auth/online-users/${encodeURIComponent(id)}/revoke/`, { current_password: currentPassword })).data.data,
}
