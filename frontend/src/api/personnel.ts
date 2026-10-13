import request, { type ApiResponse, type PagedData } from './request'

export interface Person { id: string; username: string; display_name: string; department: string | null; department_name: string | null }
export interface PickerDepartments { enabled: boolean; truncated: boolean; items: Array<{ id: string; name: string; parent: string | null }> }
export type PersonnelPurpose = 'approval' | 'post'
const urls = { approval: ['/approvals/assignees/', '/approvals/assignee-departments/'], post: ['/organization/people/', '/organization/people/departments/'] } as const
export const personnelApi = {
  people: async (purpose: PersonnelPurpose, params: { search: string; department?: string; page: number; page_size: number }, signal: AbortSignal) =>
    (await request.get<ApiResponse<PagedData<Person>>>(urls[purpose][0], { params, signal })).data.data,
  departments: async (purpose: PersonnelPurpose, signal: AbortSignal) =>
    (await request.get<ApiResponse<PickerDepartments>>(urls[purpose][1], { signal })).data.data,
}
