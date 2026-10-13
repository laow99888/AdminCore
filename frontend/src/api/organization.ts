import request, { type ApiResponse, type PagedData } from './request'
import type { ListParams } from './index'

export interface DepartmentRow { id: string; name: string; parent: string | null; order: number; is_active: boolean; version: number }
export interface MembershipRow { id: string; user: string; username: string; department: string; department_name: string; version: number }
export interface ScopeRow { id: string; role: string; role_name: string; resource: string; scope: string; departments: string[]; version: number }
export type OrganizationSection = 'departments' | 'memberships' | 'scopes'
export const organizationApi = {
  list: async <T>(section: OrganizationSection, params?: ListParams) => (await request.get<ApiResponse<PagedData<T>>>(`/organization/${section}/`, { params })).data.data,
  save: (section: OrganizationSection, id: string, data: object) => id
    ? request.patch(`/organization/${section}/${id}/`, data) : request.post(`/organization/${section}/`, data),
  remove: (section: OrganizationSection, id: string) => request.delete(`/organization/${section}/${id}/`),
}
