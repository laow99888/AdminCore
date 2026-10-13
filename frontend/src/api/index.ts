/**
 * 业务 API 模块
 * 后端约定：列表为分页响应 {code, message, data: {items, pagination}}
 */

import request, { type ApiResponse, type PagedData } from './request'

/** 为一次用户写操作生成稳定的幂等键；Axios 的 401 重放会复用同一份配置。 */
export function newIdempotencyKey(prefix = 'ui') {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `${prefix}-${suffix}`
}

// ===== 通用查询参数 =====
export interface ListParams {
  page?: number
  page_size?: number
  search?: string
  ordering?: string
  [key: string]: any
}

async function getPaged<T>(url: string, params?: ListParams): Promise<PagedData<T>> {
  const res = await request.get<ApiResponse<PagedData<T>>>(url, { params })
  return res.data.data
}

// ===== 用户管理 =====
export interface UserRow {
  id: string
  username: string
  email: string
  first_name: string
  last_name: string
  is_active: boolean
  login_count?: number
  created_at: string
}

export interface UserDetail extends UserRow {
  roles: Array<{ role__id: string; role__name: string }>
}

export const usersApi = {
  list: (params?: ListParams) => getPaged<UserRow>('/users/', params),
  detail: async (id: string): Promise<UserDetail> => (await request.get<ApiResponse<UserDetail>>(`/users/${id}/`)).data.data,
  create: (data: Partial<UserRow> & { password: string; role_ids?: string[] }) => request.post('/users/', data),
  update: (id: string, data: Partial<UserRow> & { role_ids?: string[] }) => request.patch(`/users/${id}/`, data),
  remove: (id: string) => request.delete(`/users/${id}/`),
  resetPassword: (id: string, password: string) =>
    request.post(`/users/${id}/reset_password/`, { password }),
  bulkAction: (action: string, userIds: string[]) =>
    request.post('/users/bulk_action/', { action, user_ids: userIds }),
}

// ===== 文件管理 =====
export interface FileRow {
  id: string
  original_name: string
  file: string
  file_type: string
  size: number
  size_display: string
  description: string
  uploader_name?: string
  download_count: number
  created_at: string
}

export const filesApi = {
  list: (params?: ListParams) => getPaged<FileRow>('/files/', params),
  upload: (file: File, description?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (description) form.append('description', description)
    return request.post('/files/', form)
  },
  remove: (id: string) => request.delete(`/files/${id}/`),
  purge: (id: string) => request.delete(`/files/${id}/purge/`),
  /** 使用共享请求实例的 baseURL、认证与刷新流程。 */
  downloadUrl: (id: string) => `/files/${id}/download/`,
}

// ===== 任务中心 =====
export interface TaskRow {
  id: string
  name: string
  task_type: string
  status: string
  progress: number
  result: any
  error: string
  creator_name?: string
  duration?: number | null
  created_at: string
}

export const tasksApi = {
  list: (params?: ListParams) => getPaged<TaskRow>('/tasks/', params),
  cancel: (id: string) => request.post(`/tasks/${id}/cancel/`),
  cleanupHistory: (days = 30) => request.post('/tasks/cleanup/', { days }),
}

// ===== 通知中心 =====
export interface NotificationRow {
  id: string
  title: string
  content: string
  notification_type: string
  is_read: boolean
  read_at?: string
  link: string
  created_at: string
  sender_name?: string
}

export const notificationsApi = {
  list: (params?: ListParams) => getPaged<NotificationRow>('/notifications/', params),
  unreadCount: async (): Promise<number> => {
    const res = await request.get<ApiResponse<{ count: number }>>('/notifications/unread_count/')
    return res.data.data.count
  },
  markRead: (id: string) => request.post(`/notifications/${id}/mark_read/`),
  markAllRead: () => request.post('/notifications/mark_all_read/'),
  send: (data: { recipient_ids: string[]; title: string; content?: string; notification_type?: string }, key = newIdempotencyKey('notification')) =>
    request.post('/notifications/', data, { headers: { 'Idempotency-Key': key } }),
}

// ===== 审批流程 =====
export interface ApprovalRow {
  id: string
  title: string
  request_type: string
  content: string
  applicant_name: string
  assignee_name: string
  status: string
  decided_by_name?: string
  decision_comment: string
  decided_at?: string
  created_at: string
}

export type ApprovalBox = 'todo' | 'done' | 'sent'

export const approvalsApi = {
  list: (box: ApprovalBox | undefined, params?: ListParams) =>
    getPaged<ApprovalRow>('/approvals/', { ...(box ? { box } : {}), ...params }),
  create: (data: { title: string; request_type: string; content: string; assignee_username: string }, key = newIdempotencyKey('approval-create')) =>
    request.post('/approvals/', data, { headers: { 'Idempotency-Key': key } }),
  approve: (id: string, comment = '') => request.post(`/approvals/${id}/approve/`, { comment }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-approve-${id}`) } }),
  reject: (id: string, comment = '') => request.post(`/approvals/${id}/reject/`, { comment }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-reject-${id}`) } }),
  cancel: (id: string) => request.post(`/approvals/${id}/cancel/`),
}

// ===== 数据导入导出 =====
export const dataIoApi = {
  importUsers: (file: File, resource = 'users') => {
    const form = new FormData()
    form.append('file', file)
    form.append('resource', resource)
    return request.post('/data-io/import/', form)
  },
  taskDetail: (taskId: string) => request.get(`/data-io/import/${taskId}/`),
  retryImport: (taskId: string) => request.post(`/data-io/import/${taskId}/`),
  templateUrl: (resource = 'users') => `/data-io/template/?resource=${encodeURIComponent(resource)}`,
  exportUrl: (resource = 'users', format: 'csv' | 'xlsx' = 'csv') =>
    `/data-io/export/?resource=${encodeURIComponent(resource)}&export_format=${format}`,
}

// ===== 角色与菜单 =====
export interface RoleRow {
  id: string
  name: string
  description: string
  is_active: boolean
  permissions: Array<{ id: string; name: string; code: string }>
  created_at: string
}

export interface MenuRow {
  id: string
  name: string
  path: string
  icon: string
  order: number
  is_visible: boolean
  parent?: string | null
  permission?: string | null
  children?: MenuRow[]
}

export const rolesApi = {
  list: (params?: ListParams) => getPaged<RoleRow>('/permissions/roles/', params),
  create: (data: Partial<RoleRow> & { permission_ids?: string[] }) =>
    request.post('/permissions/roles/', data),
  update: (id: string, data: Partial<RoleRow> & { permission_ids?: string[] }) =>
    request.patch(`/permissions/roles/${id}/`, data),
  remove: (id: string) => request.delete(`/permissions/roles/${id}/`),
}

export const permissionsApi = {
  list: (params?: ListParams) => getPaged<any>('/permissions/permissions/', params),
}

export const menusApi = {
  create: (data: Partial<MenuRow>) => request.post('/permissions/menus/', data),
  update: (id: string, data: Partial<MenuRow>) => request.patch(`/permissions/menus/${id}/`, data),
  remove: (id: string) => request.delete(`/permissions/menus/${id}/`),
  myMenu: async (): Promise<MenuRow[]> => {
    const res = await request.get<ApiResponse<MenuRow[]>>('/permissions/menus/my_menu/')
    return res.data.data
  },
  list: async (): Promise<MenuRow[]> => {
    const menus: MenuRow[] = []
    let page = 1
    let totalPages = 1
    do {
      const res = await request.get<ApiResponse<PagedData<MenuRow>>>('/permissions/menus/', { params: { page, page_size: 100 } })
      menus.push(...res.data.data.items)
      totalPages = res.data.data.pagination.total_pages
      page += 1
    } while (page <= totalPages)
    return menus
  },
}

// ===== 仪表盘 =====
export interface DashboardStats {
  totals: {
    users: number
    files: number
    pending_approvals: number
    unread_notifications: number
    today_logins: number
    today_operations: number
  }
  login_trend: Array<{ date: string; success: number; failed: number }>
  task_status: Record<string, number>
}

export const dashboardApi = {
  stats: async (): Promise<DashboardStats> => {
    const res = await request.get<ApiResponse<DashboardStats>>('/dashboard/stats/')
    return res.data.data
  },
}

// ===== 带认证及自动刷新的 Blob 下载 =====
export async function downloadFile(url: string, filename: string): Promise<void> {
  const res = await request.get<Blob>(url, { responseType: 'blob' })
  const blob = res.data
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(objectUrl)
}

// ===== 操作日志 =====
export interface OperationLogRow {
  id: string
  user?: string
  action: string
  resource: string
  description: string
  status: number
  created_at: string
}

export const logsApi = {
  operation: (params?: ListParams) => getPaged<OperationLogRow>('/logs/operation/', params),
  login: (params?: ListParams) => getPaged<any>('/logs/login/', params),
  exception: (params?: ListParams) => getPaged<any>('/logs/exception/', params),
}
