import request, { type ApiResponse } from './request'
import { newIdempotencyKey, type TaskRow } from './index'

export interface MaintenanceSchedule {
  key: string
  name: string
  task: string
  enabled: boolean
  module_enabled: boolean
  missing: boolean
  revision: string
  cron: { minute: string; hour: string; day_of_week: string; day_of_month: string; month_of_year: string; timezone: string }
  options: { dry_run: boolean; batch_size?: number }
  supported: boolean
  overlap: string
  time_limit_seconds: number
  preview: { id: string; result: Record<string, number | boolean>; completed_at: string } | null
  last_run: TaskRow | null
}

export const maintenanceApi = {
  list: async () => (await request.get<ApiResponse<MaintenanceSchedule[]>>('/tasks/schedules/')).data.data,
  save: async (row: MaintenanceSchedule) => (await request.patch<ApiResponse<MaintenanceSchedule>>(`/tasks/schedules/${row.key}/`, {
    revision: row.revision, enabled: row.enabled, ...row.cron, options: row.options,
  })).data.data,
  run: async (row: MaintenanceSchedule, dryRun: boolean, confirmation = '', key = newIdempotencyKey('maintenance')) =>
    (await request.post<ApiResponse<TaskRow>>(`/tasks/schedules/${row.key}/run/`, {
      revision: row.revision, options: { ...row.options, dry_run: dryRun },
      confirmation, preview_id: dryRun ? null : row.preview?.id,
    }, { headers: { 'Idempotency-Key': key } })).data.data,
}
