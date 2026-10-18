import request, { type ApiResponse } from './request'

export interface DigestReference { resource: string; label: string; object_id: string; path: string }
export interface DigestStatus { pending: number; due: number; next_due_at: string | null }
export interface DigestRefresh { processed: number; published: number; suppressed: number; summaries: number }
export interface NotificationOperations {
  window_days: number; since: string; until: string; inbox_created: number; inbox_read: number
  deliveries: Array<{ channel: string; status: string; count: number }>
  outbox: Array<{ status: string; count: number }>
  business_notices: Array<{ state: string; count: number }>
  due_notices: number; final_delivery_receipts_supported: boolean
}
export interface BusinessNoticeWrite { resource: string; object_id: string; event_id: string; recipient_ids: string[] }
export interface BusinessNoticeResult { created: number; replayed: number; pending: number; published: number; suppressed: number }
export interface NoticeSearchGroup { source: string; title: string; path: string; items: Array<{ id: string; title: string }> }

export const notificationDigestsApi = {
  async status(signal?: AbortSignal) { return (await request.get<ApiResponse<DigestStatus>>('/notifications/digests/status/', { signal })).data.data },
  async refresh(signal?: AbortSignal) { return (await request.post<ApiResponse<DigestRefresh>>('/notifications/digests/refresh/', {}, { signal })).data.data },
  async detail(id: string, signal?: AbortSignal) { return (await request.get<ApiResponse<{ items: DigestReference[]; authorization_checked_at: string }>>(`/notifications/digests/${id}/`, { signal })).data.data },
  async operations(days: number, signal?: AbortSignal) { return (await request.get<ApiResponse<NotificationOperations>>('/notifications/operations/', { params: { days }, signal })).data.data },
  async send(body: BusinessNoticeWrite, signal?: AbortSignal) { return (await request.post<ApiResponse<BusinessNoticeResult>>('/notifications/business-notices/', body, { signal })).data.data },
  async search(q: string, signal?: AbortSignal) { return (await request.get<ApiResponse<{ groups: NoticeSearchGroup[] }>>('/business-search/', { params: { q }, signal })).data.data.groups },
}
