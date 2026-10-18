import request, { type ApiResponse } from './request'

export interface FileRevision {
  number: number; file_id: string; original_name: string; size: number
  created_at: string; restored_from: number | null
}
export interface FileHistory { version: number; current_file: string; items: FileRevision[]; has_more: boolean }
export interface FileCapacity { used_bytes: number; limit_bytes: number; remaining_bytes: number | null; version: number }
export const fileDocumentsApi = {
  history: async (id: string, page: number, signal?: AbortSignal) =>
    (await request.get<ApiResponse<FileHistory>>(`/files/${id}/versions/`, { params: { page }, signal })).data.data,
  append: async (id: string, values: { version: number; file_id: string } | { version: number; restore_number: number }) =>
    (await request.post<ApiResponse<FileHistory>>(`/files/${id}/versions/`, values)).data.data,
  capacity: async (ownerId?: string, signal?: AbortSignal) =>
    (await request.get<ApiResponse<FileCapacity>>('/files/capacity/', { params: ownerId ? { owner_id: ownerId } : {}, signal })).data.data,
  saveCapacity: async (ownerId: string, limitBytes: number, version: number) =>
    (await request.put<ApiResponse<FileCapacity>>('/files/capacity/', { owner_id: ownerId, limit_bytes: limitBytes, version })).data.data,
}

export function fileBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(2)} MiB`
  return `${(value / 1024 ** 3).toFixed(2)} GiB`
}
