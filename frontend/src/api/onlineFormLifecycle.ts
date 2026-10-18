import request, { type ApiResponse, type PagedData } from './request'
import type { OnlineFormDefinition, OnlineFormRecordRow, OnlineFormRow } from './index'

export type ReleasedOnlineForm = OnlineFormRow & { release_number?: number; approval_flow_code?: string; approval_flow?: string | null; approval_flow_version?: number | null }
export type OnlineFormHistoryRow = OnlineFormRecordRow & {
  form_name: string
  release_number: number
  form_status: OnlineFormRow['status']
  approval_status?: 'draft' | 'pending' | 'approved' | 'rejected' | 'cancelled'
  approval_request?: string | null
  approval_enabled?: boolean
}
export type OnlineFormHistoryDetail = OnlineFormHistoryRow & { definition_snapshot: OnlineFormDefinition }

const recordsUrl = (code: string) => `/online-forms/${encodeURIComponent(code)}/records/`
export const onlineFormLifecycleApi = {
  approvalFlows: async (formId?: string) => (await request.get<ApiResponse<{ code: string; name: string; revision: number }[]>>(
    '/online-forms/approval-flows/', { params: formId ? { form_id: formId } : {} })).data.data,
  submitApproval: async (code: string, id: string, version: number) => (await request.post<ApiResponse<OnlineFormHistoryDetail>>(
    `${recordsUrl(code)}${id}/submit-approval/`, { version })).data.data,
  withdrawApproval: async (code: string, id: string, version: number) => (await request.post<ApiResponse<OnlineFormHistoryDetail>>(
    `${recordsUrl(code)}${id}/withdraw-approval/`, { version })).data.data,
  newVersion: async (id: string, version: number) => (await request.post<ApiResponse<ReleasedOnlineForm>>(
    `/online-forms/forms/${id}/new-version/`, { version })).data.data,
  records: async (code: string, page = 1) => (await request.get<ApiResponse<PagedData<OnlineFormHistoryRow>>>(
    recordsUrl(code), { params: { page, page_size: 20 } })).data.data,
  detail: async (code: string, id: string) => (await request.get<ApiResponse<OnlineFormHistoryDetail>>(
    `${recordsUrl(code)}${id}/`)).data.data,
  update: async (code: string, id: string, data: Record<string, unknown>, version: number) => (
    await request.patch<ApiResponse<OnlineFormHistoryDetail>>(`${recordsUrl(code)}${id}/`, { data, version })).data.data,
}
