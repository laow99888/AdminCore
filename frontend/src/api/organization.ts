import request, { type ApiResponse, type PagedData } from './request'
import type { ListParams } from './index'

export interface DepartmentRow { id: string; name: string; parent: string | null; order: number; is_active: boolean; version: number; leader?: string | null; leader_name?: string | null }
export interface MembershipRow { id: string; user: string; username: string; department: string; department_name: string; version: number }
export interface ScopeRow { id: string; role: string; role_name: string; resource: string; scope: string; departments: string[]; version: number }
export type OrganizationSection = 'departments' | 'memberships' | 'scopes'
export const organizationApi = {
  list: async <T>(section: OrganizationSection, params?: ListParams) => (await request.get<ApiResponse<PagedData<T>>>(`/organization/${section}/`, { params })).data.data,
  detail: async <T>(section: OrganizationSection, id: string, signal?: AbortSignal) => (await request.get<ApiResponse<T>>(`/organization/${section}/${id}/`, { signal })).data.data,
  save: (section: OrganizationSection, id: string, data: object) => id
    ? request.patch(`/organization/${section}/${id}/`, data) : request.post(`/organization/${section}/`, data),
  remove: (section: OrganizationSection, id: string) => request.delete(`/organization/${section}/${id}/`),
}

export interface AppointmentRow {
  id: string; user: string; username: string; department: string; department_name: string
  kind: 'primary' | 'secondary'; starts_on: string; ends_on: string | null; cancelled: boolean; reason: string; version: number
  status: 'cancelled' | 'planned' | 'ended' | 'active'
}
export const appointmentsApi = {
  list: async (params: { page: number; page_size: number; search?: string; as_of?: string }, signal?: AbortSignal) =>
    (await request.get<ApiResponse<PagedData<AppointmentRow>>>('/organization/appointments/', { params, signal })).data.data,
  create: (data: { user: string; department: string; kind: AppointmentRow['kind']; starts_on: string; ends_on: string | null; reason: string; version: 0 }) => request.post('/organization/appointments/', data),
  finish: (id: string, operation: 'end' | 'cancel', data: { version: number; reason: string; ends_on?: string }) => request.post(`/organization/appointments/${id}/${operation}/`, data),
}
