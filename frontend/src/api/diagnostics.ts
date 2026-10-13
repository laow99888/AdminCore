import request, { type ApiResponse } from './request'

export interface ServiceProbe { name: string; status: 'ok' | 'unavailable' | 'in_process' | 'disabled'; version: string | null; latency_ms: number | null }
export interface SystemInformation {
  sampled_at: string; python: string; os: string; architecture: string; environment: string; debug: boolean
  preset: string; modules: string[]; timezone: string; database: string; storage: string
  dependencies: { name: string; version: string | null }[]; services: ServiceProbe[]
}
export interface SystemMonitor {
  sampled_at: string; scope: 'container' | 'host'
  cpu: { capacity_cores: number | null; percent: number | null; sample_seconds: number | null }
  memory: { used_bytes: number | null; total_bytes: number | null; percent: number | null }
  disks: { name: string; status: 'ok' | 'unavailable'; total_bytes: number | null; used_bytes: number | null; free_bytes: number | null; percent: number | null }[]
  processes: { pid: number; kind: 'python' | 'other'; state: string; cpu_seconds: number; rss_bytes: number; uptime_seconds: number }[]
  processes_supported: boolean; processes_truncated: boolean
}
export const diagnosticsApi = {
  information: async () => (await request.get<ApiResponse<SystemInformation>>('/system/information/')).data.data,
  monitor: async () => (await request.get<ApiResponse<SystemMonitor>>('/system/monitor/')).data.data,
}
