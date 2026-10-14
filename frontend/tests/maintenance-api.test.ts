import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), patch: vi.fn(), post: vi.fn() } }))
import request from '../src/api/request'
import { maintenanceApi, type MaintenanceSchedule } from '../src/api/maintenance'

function schedule(key = 'files'): MaintenanceSchedule {
  return { key, name: '维护任务', task: 'tasks.fixture', enabled: false, module_enabled: true, missing: false,
    revision: 'v1', cron: { minute: '0', hour: '3', day_of_week: '*', day_of_month: '*', month_of_year: '*', timezone: 'Asia/Shanghai' },
    options: { dry_run: false, batch_size: 100 }, supported: true, overlap: 'skip', time_limit_seconds: key === 'backup' ? 7200 : 300,
    requires_preview: key !== 'backup', confirmation: key === 'backup' ? '执行备份' : '执行清理',
    preview: { id: 'preview-1', result: { dry_run: true }, completed_at: '' }, last_run: null }
}

describe('维护计划 API 参数契约', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(request.post).mockResolvedValue({ data: { data: { id: 'run-1', status: 'pending' } } })
    vi.mocked(request.patch).mockResolvedValue({ data: { data: schedule() } })
  })
  it('清理执行保留文件批大小、有效预览与固定幂等键', async () => {
    await maintenanceApi.run(schedule(), false, '执行清理', 'attempt-1')
    expect(request.post).toHaveBeenCalledWith('/tasks/schedules/files/run/', {
      revision: 'v1', options: { dry_run: false, batch_size: 100 }, confirmation: '执行清理', preview_id: 'preview-1',
    }, { headers: { 'Idempotency-Key': 'attempt-1' } })
  })
  it('备份无预览即可执行，忽略清理参数和遗留预览', async () => {
    const row = schedule('backup')
    expect(await maintenanceApi.run(row, false, '执行备份', 'backup-attempt')).toMatchObject({ status: 'pending' })
    expect(request.post).toHaveBeenCalledWith('/tasks/schedules/backup/run/', {
      revision: 'v1', options: { dry_run: false }, confirmation: '执行备份', preview_id: null,
    }, { headers: { 'Idempotency-Key': 'backup-attempt' } })
    await maintenanceApi.save(row)
    expect(request.patch).toHaveBeenCalledWith('/tasks/schedules/backup/', {
      revision: 'v1', enabled: false, ...row.cron, options: { dry_run: false },
    })
  })
  it('备份和通知预览只发送 dry_run，预览请求不携带清理授权', async () => {
    for (const key of ['backup', 'notifications']) {
      await maintenanceApi.run(schedule(key), true, '', 'preview-attempt')
      expect(request.post).toHaveBeenLastCalledWith(`/tasks/schedules/${key}/run/`, {
        revision: 'v1', options: { dry_run: true }, confirmation: '', preview_id: null,
      }, { headers: { 'Idempotency-Key': 'preview-attempt' } })
    }
  })
})
