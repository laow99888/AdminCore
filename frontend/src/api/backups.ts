import request, { type ApiResponse } from './request'

export interface BackupArtifact { timestamp: string; created_at: string; artifacts: Array<Record<string, unknown>>; remote_copy: boolean }
export interface BackupStatus {
  enabled: boolean; state: string; directory_label: string; stage: string; last_error: string; last_seen_at: string | null
  artifacts: BackupArtifact[]; restore_requests: Array<{ id: string; timestamp: string; status: string; error: string; created_at: string; completed_at: string | null }>
}
export const backupsApi = {
  status: async (signal?: AbortSignal) => (await request.get<ApiResponse<BackupStatus>>('/tasks/backups/', { signal })).data.data,
  preflight: async (timestamp: string, signal?: AbortSignal) => (await request.post<ApiResponse<{ preflight_id: string; timestamp: string; artifacts: unknown[]; remote_copy: boolean }>>(`/tasks/backups/${timestamp}/preflight/`, {}, { signal })).data.data,
  restore: async (timestamp: string, preflightId: string, currentPassword: string, signal?: AbortSignal) => (await request.post<ApiResponse<{ id: string; status: string }>>(`/tasks/backups/${timestamp}/restore/`, { preflight_id: preflightId, confirmation: '恢复备份', current_password: currentPassword }, { signal })).data.data,
  request: async (id: string, signal?: AbortSignal) => (await request.get<ApiResponse<Record<string, unknown>>>(`/tasks/backups/restore-requests/${id}/`, { signal })).data.data,
}
