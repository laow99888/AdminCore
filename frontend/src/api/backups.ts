import { sdk } from './sdk'
import type { components } from './generated/schema'

export type BackupArtifact = components['schemas']['BackupArtifact']
export type BackupStatus = components['schemas']['BackupStatus']
export const backupsApi = {
  status: async (signal?: AbortSignal) => (await sdk('tasks_backups_retrieve', { signal })).data,
  preflight: async (timestamp: string, signal?: AbortSignal) => (await sdk('tasks_backups_preflight_create', { path: { timestamp }, signal })).data,
  restore: async (timestamp: string, preflightId: string, currentPassword: string, signal?: AbortSignal) => (await sdk('tasks_backups_restore_create', { path: { timestamp }, body: { preflight_id: preflightId, confirmation: '恢复备份', current_password: currentPassword }, signal })).data,
  request: async (requestId: string, signal?: AbortSignal) => (await sdk('tasks_backups_restore_requests_retrieve', { path: { request_id: requestId }, signal })).data,
}
