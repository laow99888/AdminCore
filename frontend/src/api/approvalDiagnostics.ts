import request, { type ApiResponse } from './request'
import type { ApprovalRow } from './index'

export interface ApprovalIssue {
  code: string
  severity: 'warning' | 'blocked'
  node: string
  step_id: string | null
  step_version: number | null
}
export interface ApprovalDiagnostic {
  request_id: string
  workflow_version: number
  checked_at: string
  scope: 'current' | 'current_and_future'
  blocked: boolean
  issues: ApprovalIssue[]
}
export interface ApprovalHealth {
  checked_at: string
  scanned: number
  next_cursor: string | null
  items: ApprovalDiagnostic[]
}
export const approvalDiagnosticsApi = {
  repairLegacy(id: string, target: string, version: number, comment: string) {
    return request.post<ApiResponse<ApprovalRow>>(`/approvals/${id}/repair-step/`, { target_user_id: target, expected_workflow_version: version, comment })
  },
  async request(id: string): Promise<ApprovalDiagnostic> {
    return (await request.get<ApiResponse<ApprovalDiagnostic>>(`/approvals/${id}/diagnostics/`)).data.data
  },
  async health(cursor?: string): Promise<ApprovalHealth> {
    return (await request.get<ApiResponse<ApprovalHealth>>('/approvals/health/', { params: { limit: 25, ...(cursor ? { cursor } : {}) } })).data.data
  },
}
