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
  requires_preview: boolean
  confirmation: string
  preview: { id: string; result: Record<string, number | boolean | string>; completed_at: string } | null
  last_run: TaskRow | null
}

export const maintenanceApi = {
  list: async () => (await request.get<ApiResponse<MaintenanceSchedule[]>>('/tasks/schedules/')).data.data,
  save: async (row: MaintenanceSchedule) => (await request.patch<ApiResponse<MaintenanceSchedule>>(`/tasks/schedules/${row.key}/`, {
    revision: row.revision, enabled: row.enabled, ...row.cron,
    options: row.key === 'files' ? { dry_run: row.options.dry_run, batch_size: row.options.batch_size } : { dry_run: row.options.dry_run },
  })).data.data,
  run: async (row: MaintenanceSchedule, dryRun: boolean, confirmation = '', key = newIdempotencyKey('maintenance')) =>
    (await request.post<ApiResponse<TaskRow>>(`/tasks/schedules/${row.key}/run/`, {
      revision: row.revision, options: row.key === 'files' ? { dry_run: dryRun, batch_size: row.options.batch_size } : { dry_run: dryRun },
      confirmation, preview_id: !dryRun && row.requires_preview ? row.preview?.id : null,
    }, { headers: { 'Idempotency-Key': key } })).data.data,
}
