import request, { type ApiResponse, type PagedData } from './request'

export interface MessageVersion { id: string; number: number; subject: string; body: string; variables: string[]; created_at: string }
export interface MessageTemplate { id: string; code: string; name: string; enabled: boolean; revision: number; current: MessageVersion }
export interface MessageDraft { code: string; name: string; enabled: boolean; revision: number; subject: string; body: string; variables: string[] }
export type MessageChannel = 'inapp' | 'email' | 'webhook' | 'sms'
export interface MessageDelivery { id: string; template_code: string; version_number: number; recipient: string | null; channel: MessageChannel; status: 'pending' | 'succeeded' | 'failed' | 'terminated'; attempts: number; last_error: string; request_id: string; created_at: string; expires_at: string }
export interface MessagePreview { subject: string; body: string }
const base = '/notifications/templates/', deliveryBase = '/notifications/deliveries/'
export const messagesApi = {
  list: async (params: { page: number; page_size: number; search: string }, signal: AbortSignal) => (await request.get<ApiResponse<PagedData<MessageTemplate>>>(base, { params, signal })).data.data,
  detail: async (id: string, signal?: AbortSignal) => (await request.get<ApiResponse<MessageTemplate>>(`${base}${id}/`, { signal })).data.data,
  save: async (id: string, data: MessageDraft) => (await request.request<ApiResponse<MessageTemplate>>({ url: base + (id ? `${id}/` : ''), method: id ? 'patch' : 'post', data })).data.data,
  versions: async (id: string, page: number, signal: AbortSignal) => (await request.get<ApiResponse<PagedData<MessageVersion>>>(`${base}${id}/versions/`, { params: { page, page_size: 10 }, signal })).data.data,
  channels: async (signal: AbortSignal) => (await request.get<ApiResponse<Array<{ key: MessageChannel; enabled: boolean }>>>(`${base}channels/`, { signal })).data.data,
  preview: async (id: string, revision: number, values: Record<string, string>, signal: AbortSignal) => (await request.post<ApiResponse<MessagePreview>>(`${base}${id}/preview/`, { revision, values }, { signal })).data.data,
  send: async (id: string, data: { revision: number; values: Record<string, string>; recipient_ids: string[]; channels: MessageChannel[] }, key: string) => (await request.post<ApiResponse<{ count: number }>>(`${base}${id}/send/`, data, { headers: { 'Idempotency-Key': key } })).data.data,
  deliveries: async (params: { page: number; page_size: number; status: string }, signal: AbortSignal) => (await request.get<ApiResponse<PagedData<MessageDelivery>>>(deliveryBase, { params, signal })).data.data,
  retry: async (id: string) => (await request.post<ApiResponse<MessageDelivery>>(`${deliveryBase}${id}/retry/`)).data.data,
}
