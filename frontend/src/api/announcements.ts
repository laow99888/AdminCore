import request, { type ApiResponse, type PagedData } from './request'
import { newIdempotencyKey } from './index'
export type AnnouncementContentFormat = 'plain' | 'html'
export interface AnnouncementRow { id: string; title: string; content: string; content_format?: AnnouncementContentFormat; status: 'draft' | 'published' | 'withdrawn'; version: number; published_at: string | null; created_at: string; updated_at: string }
export interface AnnouncementDraft { title: string; content: string; content_format?: AnnouncementContentFormat; version: number }
const base = '/notifications/announcements/'
export const announcementsApi = {
  list: async (manage: boolean, params: { page: number; page_size: number; search: string; status?: string }, signal?: AbortSignal) =>
    (await request.get<ApiResponse<PagedData<AnnouncementRow>>>(manage ? `${base}manage/` : base, { params, signal })).data.data,
  detail: async (id: string, manage: boolean, signal?: AbortSignal) =>
    (await request.get<ApiResponse<AnnouncementRow>>(`${base}${manage ? 'manage/' : ''}${id}/`, { signal })).data.data,
  save: async (id: string, data: AnnouncementDraft, key: string) =>
    (await request.request<ApiResponse<AnnouncementRow>>({ url: `${base}manage/${id ? `${id}/` : ''}`, method: id ? 'patch' : 'post', data, headers: { 'Idempotency-Key': key } })).data.data,
  transition: async (row: AnnouncementRow, operation: 'publish' | 'withdraw') =>
    (await request.post<ApiResponse<AnnouncementRow>>(`${base}manage/${row.id}/${operation}/`, { version: row.version }, { headers: { 'Idempotency-Key': newIdempotencyKey(`announcement-${operation}`) } })).data.data,
}
