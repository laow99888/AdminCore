/**
 * 业务 API 模块
 * 后端约定：列表为分页响应 {code, message, data: {items, pagination}}
 */

import request, { type ApiResponse, type PagedData } from './request'
import type { ReportOutput, ReportRunOptions, ReportDetails, ReportFieldType } from './reportTypes'

/** 为一次用户写操作生成稳定的幂等键；Axios 的 401 重放会复用同一份配置。 */
export function newIdempotencyKey(prefix = 'ui') {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `${prefix}-${suffix}`
}

export interface ExampleWorkItem {
  id: string
  title: string
  notes: string
  status: 'open' | 'done'
  priority: 'normal' | 'high'
  creator: string
  creator_name: string
  version: number
  created_at: string
}
export type ExampleWrite = Pick<ExampleWorkItem, 'title' | 'notes' | 'status' | 'priority' | 'version'>
export const exampleApi = {
  list: (params?: ListParams) => getPaged<ExampleWorkItem>('/example/items/', params),
  detail: async (id: string, signal?: AbortSignal) => (await request.get<ApiResponse<ExampleWorkItem>>(`/example/items/${id}/`, { signal })).data.data,
  save: (id: string, data: ExampleWrite, key: string) => id ? request.patch(`/example/items/${id}/`, data)
    : request.post('/example/items/', data, { headers: { 'Idempotency-Key': key } }),
  remove: (id: string, version: number) => request.delete(`/example/items/${id}/`, { data: { version } }),
}

// ===== 通用查询参数 =====
export interface ListParams {
  page?: number
  page_size?: number
  search?: string
  ordering?: string
  [key: string]: unknown
}

async function getPaged<T>(url: string, params?: ListParams): Promise<PagedData<T>> {
  const res = await request.get<ApiResponse<PagedData<T>>>(url, { params })
  return res.data.data
}

// ===== 用户管理 =====
export interface UserRow {
  version: number
  id: string
  username: string
  email: string
  phone?: string
  first_name: string
  last_name: string
  is_active: boolean
  login_count?: number
  created_at: string
}

export interface UserDetail extends UserRow {
  roles: Array<{ role__id: string; role__name: string }>
}

export interface AtomicUserBulkResult {
  atomic: true
  succeeded: number
  failed: number
  results: Array<{ id: string; status: number }>
}

export const usersApi = {
  list: (params?: ListParams) => getPaged<UserRow>('/users/', params),
  detail: async (id: string, signal?: AbortSignal): Promise<UserDetail> => (await request.get<ApiResponse<UserDetail>>(`/users/${id}/`, { signal })).data.data,
  sensitive: async (id: string, currentPassword: string, signal?: AbortSignal): Promise<{ email: string; phone: string }> =>
    (await request.post<ApiResponse<{ email: string; phone: string }>>(`/users/${id}/sensitive/`, { current_password: currentPassword }, { signal })).data.data,
  create: (data: Partial<UserRow> & { password: string; role_ids?: string[]; must_change_password?: boolean }) => request.post('/users/', data),
  update: (id: string, data: Partial<UserRow> & { version: number; role_ids?: string[] }) => request.patch(`/users/${id}/`, data),
  remove: (id: string) => request.delete(`/users/${id}/`),
  resetPassword: (id: string, password: string, mustChangePassword = true) =>
    request.post(`/users/${id}/reset_password/`, { password, must_change_password: mustChangePassword }),
  bulkAction: (action: 'activate' | 'deactivate' | 'delete', userIds: string[]) =>
    request.post<ApiResponse<AtomicUserBulkResult>>('/users/bulk_action/', { action, user_ids: userIds }),
}

// ===== 文件管理 =====
export interface FileRow {
  organization?: import('./fileLibrary').FileOrganization
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
  is_deleted: boolean
  deleted_at: string | null
  lifecycle_version: number
}

export interface RecycleResult {
  results: Array<{ id: string; status: number; message: string; original_name?: string; size?: number }>
  dry_run: boolean
  succeeded: number
  failed: number
}

export const filesApi = {
  list: (params?: ListParams) => getPaged<FileRow>('/files/', params),
  recycle: (params?: ListParams) => getPaged<FileRow>('/files/recycle/', params),
  recyclePolicy: async (): Promise<{ retention_days: number; cleanup_enabled: boolean }> =>
    (await request.get<ApiResponse<{ retention_days: number; cleanup_enabled: boolean }>>('/files/recycle_policy/')).data.data,
  recycleAction: async (action: 'restore' | 'purge', rows: FileRow[], dryRun = false, confirmation = ''): Promise<RecycleResult> =>
    (await request.post<ApiResponse<RecycleResult>>('/files/recycle_action/', {
      action, items: rows.map(row => ({ id: row.id, lifecycle_version: row.lifecycle_version })),
      dry_run: dryRun, confirmation,
    })).data.data,
  upload: (file: File, description?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (description) form.append('description', description)
    return request.post<ApiResponse<FileRow>>('/files/', form)
  },
  remove: (id: string) => request.delete(`/files/${id}/`),
  purge: (id: string) => request.delete(`/files/${id}/purge/`),
  /** 使用共享请求实例的 baseURL、认证与刷新流程。 */
  downloadUrl: (id: string) => `/files/${id}/download/`,
}

// ===== 任务中心 =====
export interface TaskRow {
  request_id?: string
  id: string
  name: string
  task_type: string
  status: string
  progress: number
  result: unknown
  error: string
  creator_name?: string
  duration?: number | null
  created_at: string
  related_resource?: string
  creator?: string | null
  execution?: { attempt: number; can_resume: boolean; semantics: string; policy: { soft_timeout: number; hard_timeout: number; dispatch_attempts: number; automatic_execution_retries: number } } | null
}

export const tasksApi = {
  list: (params?: ListParams) => getPaged<TaskRow>('/tasks/', params),
  cancel: (id: string) => request.post(`/tasks/${id}/cancel/`),
  resume: (id: string) => request.post(`/tasks/${id}/resume/`),
  cleanupHistory: (days = 30, options: { dry_run?: boolean; batch_size?: number; preview_token?: string; confirmation?: string } = {}) =>
    request.post('/tasks/cleanup/', { days, dry_run: true, ...options }),
}

// ===== 报表与大屏 =====
export interface ReportDefinition {
  id: string
  name: string
  code: string
  kind: 'report' | 'dashboard'
  status: 'draft' | 'published' | 'archived'
  version: number
  definition: Record<string, unknown>
  created_at: string
  updated_at: string
}
export interface ReportCatalogItem { key: string; label: string; dimensions: string[]; metrics: string[]; filters: string[]; field_types?: Record<string, ReportFieldType> }
export const reportsApi = {
  catalog: async (): Promise<ReportCatalogItem[]> => (await request.get<ApiResponse<ReportCatalogItem[]>>('/reports/catalog/')).data.data,
  list: (params?: ListParams) => getPaged<ReportDefinition>('/reports/definitions/', params),
  create: (data: Pick<ReportDefinition, 'name' | 'code' | 'kind' | 'definition'>) => request.post<ApiResponse<ReportDefinition>>('/reports/definitions/', data),
  update: (id: string, data: Partial<Pick<ReportDefinition, 'name' | 'kind' | 'definition'>> & { version: number }) => request.patch<ApiResponse<ReportDefinition>>(`/reports/definitions/${id}/`, data),
  publish: (id: string, version?: number) => request.post<ApiResponse<ReportDefinition>>(`/reports/definitions/${id}/publish/`, { version }),
  run: async (id: string, options?: ReportRunOptions, signal?: AbortSignal): Promise<ReportOutput> => options
    ? (await request.post<ApiResponse<ReportOutput>>(`/reports/definitions/${id}/run/`, options, { signal })).data.data
    : (await request.get<ApiResponse<ReportOutput>>(`/reports/definitions/${id}/run/`, { signal })).data.data,
  details: async (id: string, data: { widget?: string; options?: ReportRunOptions; group: Record<string, unknown>; page: number; page_size: number }, signal?: AbortSignal): Promise<ReportDetails> => (await request.post<ApiResponse<ReportDetails>>(`/reports/definitions/${id}/details/`, data, { signal })).data.data,
}

// ===== 通知中心 =====
export interface OutboxEventRow {
  id: string
  topic: string
  status: 'pending' | 'processing' | 'failed' | 'succeeded'
  attempts: number
  available_at: string
  last_error: string
  request_id: string
  published_at: string | null
  created_at: string
  updated_at: string
}

export const reliableEventsApi = {
  list: (params?: ListParams) => getPaged<OutboxEventRow>('/reliability/events/', params),
  detail: async (id: string): Promise<OutboxEventRow> =>
    (await request.get<ApiResponse<OutboxEventRow>>(`/reliability/events/${id}/`)).data.data,
  retry: (id: string) => request.post(`/reliability/events/${id}/retry/`),
}

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
  flow?: string | null
  flow_name?: string | null
  flow_version?: number | null
  business_module?: string
  business_record_id?: string | null
  business_snapshot?: Record<string, unknown>
  extra_data?: Record<string, unknown> | null
  current_node?: string
  workflow_version?: number
  flow_revision?: number | null
  return_count?: number
  returnable_nodes?: string[]
  steps?: ApprovalStepRow[]
  cc_recipients?: Array<{ id: string; user: string; user_name: string }>
}

export interface ApprovalStepRow {
  assignment_context?: { source?: string; levels?: number; department_name?: string; source_department_name?: string; resolved_on?: string; assignee_name?: string }
  id: string
  node_key: string
  kind: 'user' | 'parallel' | 'or'
  mode: 'all' | 'any'
  sequence: number
  status: string
  assignee?: string | null
  assignee_name?: string | null
  delegated_to?: string | null
  delegated_to_name?: string | null
  version: number
  due_at?: string | null
  escalate_at?: string | null
  escalation_user?: string | null
  reminded_at?: string | null
  escalated_at?: string | null
  timeout_error?: string
}

export interface ApprovalFlowRow {
  id: string
  name: string
  code: string
  status: 'draft' | 'published' | 'archived'
  version: number
  revision?: number
  definition: { schema_version?: 2; inputs?: Array<{ key: string; type: string }>; nodes: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>> }
}

export type ApprovalBox = 'todo' | 'done' | 'sent' | 'cc' | 'exceptions'

export const approvalsApi = {
  list: (box: ApprovalBox | undefined, params?: ListParams) =>
    getPaged<ApprovalRow>('/approvals/', { ...(box ? { box } : {}), ...params }),
  create: (data: { title: string; request_type: string; content: string; flow_id?: string; extra_data?: Record<string, unknown> } & ({ assignee_id: string; assignee_username?: never } | { assignee_username: string; assignee_id?: never } | { assignee_id?: never; assignee_username?: never }), key = newIdempotencyKey('approval-create')) =>
    request.post('/approvals/', data, { headers: { 'Idempotency-Key': key } }),
  approve: (id: string, comment = '', expected_workflow_version?: number, step_id?: string) => request.post(`/approvals/${id}/approve/`, { comment, expected_workflow_version, step_id }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-approve-${id}`) } }),
  reject: (id: string, comment = '', expected_workflow_version?: number, step_id?: string) => request.post(`/approvals/${id}/reject/`, { comment, expected_workflow_version, step_id }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-reject-${id}`) } }),
  history: (id: string, params?: ListParams) => getPaged<ApprovalHistoryRow>(`/approvals/${id}/history/`, params),
  returnNode: (id: string, target_node: string, expected_workflow_version: number, comment: string, key = newIdempotencyKey('approval-return')) => request.post(`/approvals/${id}/return-node/`, { target_node, expected_workflow_version, comment }, { headers: { 'Idempotency-Key': key } }),
  retryTimeout: (id: string, step_id: string, expected_version: number, comment: string, target_user_id?: string) => request.post(`/approvals/${id}/retry-timeout/`, { step_id, expected_version, comment, target_user_id }, { headers: { 'Idempotency-Key': newIdempotencyKey('approval-timeout') } }),
  cancel: (id: string) => request.post(`/approvals/${id}/cancel/`),
  repairStep: (id: string, target_user_id: string, step_id: string, expected_version: number, comment = '') => request.post(`/approvals/${id}/repair-step/`, { target_user_id, step_id, expected_version, comment }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-repair-${id}`) } }),
  addSign: (id: string, target_user_id: string, comment = '', expected_version?: number, expected_workflow_version?: number) => request.post(`/approvals/${id}/add-sign/`, { target_user_id, comment, expected_version, expected_workflow_version }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-add-sign-${id}`) } }),
  transfer: (id: string, target_user_id: string, comment = '', expected_version?: number, expected_workflow_version?: number) => request.post(`/approvals/${id}/transfer/`, { target_user_id, comment, expected_version, expected_workflow_version }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-transfer-${id}`) } }),
  delegate: (id: string, target_user_id: string, comment = '', expected_version?: number, expected_workflow_version?: number) => request.post(`/approvals/${id}/delegate/`, { target_user_id, comment, expected_version, expected_workflow_version }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-delegate-${id}`) } }),
  cc: (id: string, user_ids: string[], comment = '') => request.post(`/approvals/${id}/cc/`, { user_ids, comment }, { headers: { 'Idempotency-Key': newIdempotencyKey(`approval-cc-${id}`) } }),
}

export const approvalFlowsApi = {
  list: (params?: ListParams) => getPaged<ApprovalFlowRow>('/approvals/flows/', params),
  create: (data: Pick<ApprovalFlowRow, 'name' | 'code' | 'definition'>) => request.post('/approvals/flows/', data),
  update: (id: string, data: Pick<ApprovalFlowRow, 'name' | 'code' | 'definition' | 'version'>) => request.put(`/approvals/flows/${id}/`, data),
  publish: (id: string, version?: number) => request.post(`/approvals/flows/${id}/publish/`, { version }),
  archive: (id: string) => request.post(`/approvals/flows/${id}/archive/`),
  newRevision: (id: string, key = newIdempotencyKey('approval-revision')) => request.post(`/approvals/flows/${id}/new-revision/`, {}, { headers: { 'Idempotency-Key': key } }),
}

export interface ApprovalHistoryRow {
  id: string
  action: string
  actor_name: string | null
  target_user_name: string | null
  comment: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface OnlineFormCondition { field: string; op: 'eq' | 'ne' | 'in' | 'empty' | 'not_empty' | 'lt' | 'lte' | 'gt' | 'gte'; value?: unknown }
export interface OnlineFormRule { left: string; op: 'lt' | 'lte' | 'gt' | 'gte' | 'eq'; right: string; message: string }
export type OnlineFormOperand = { field: string } | { literal: string }
export type OnlineFormComputation = { op: 'add' | 'subtract' | 'multiply' | 'divide'; operands: [OnlineFormOperand, OnlineFormOperand] } | { op: 'sum'; detail: string; field: string }
export interface OnlineFormField { key: string; label: string; type: 'text' | 'textarea' | 'number' | 'select' | 'date' | 'boolean' | 'decimal' | 'datetime' | 'multiselect' | 'detail' | 'file' | 'relation'; resource?: string; required: boolean; default?: unknown; options?: string[]; max_length?: number; min?: number | string; max?: number | string; scale?: number; section?: string; span?: 1 | 2; help?: string; placeholder?: string; visible_when?: OnlineFormCondition[]; required_when?: OnlineFormCondition[]; fields?: OnlineFormField[]; min_rows?: number; max_rows?: number; rules?: OnlineFormRule[]; computation?: OnlineFormComputation }
export interface OnlineFormDefinition { schema_version?: 2; fields: OnlineFormField[]; sections?: { key: string; title: string }[]; rules?: OnlineFormRule[] }
export interface OnlineFormRow { id: string; name: string; code: string; status: 'draft' | 'published' | 'archived'; version: number; definition: OnlineFormDefinition }
export interface OnlineFormRecordRow { id: string; form: string; form_version: number; owner: string; owner_name?: string; data: Record<string, unknown>; version: number; created_at: string; updated_at: string }
export const onlineFormsApi = {
  list: (params?: ListParams) => getPaged<OnlineFormRow>('/online-forms/forms/', params),
  create: (data: Pick<OnlineFormRow, 'name' | 'code' | 'definition'>) => request.post('/online-forms/forms/', data),
  update: (id: string, data: Pick<OnlineFormRow, 'name' | 'code' | 'definition' | 'version'>) => request.put(`/online-forms/forms/${id}/`, data),
  publish: (id: string, version?: number) => request.post(`/online-forms/forms/${id}/publish/`, { version }),
  archive: (id: string) => request.post(`/online-forms/forms/${id}/archive/`),
  validate: (definition: OnlineFormDefinition, data?: Record<string, unknown>) => request.post<ApiResponse<{ definition: OnlineFormDefinition; data?: Record<string, unknown> }>>('/online-forms/validate/', { definition, ...(data === undefined ? {} : { data }) }),
  published: (code: string) => request.get<ApiResponse<OnlineFormRow>>(`/online-forms/published/${encodeURIComponent(code)}/`),
  records: (code: string, params?: ListParams) => getPaged<OnlineFormRecordRow>(`/online-forms/${encodeURIComponent(code)}/records/`, params),
  createRecord: (code: string, data: Record<string, unknown>, key = newIdempotencyKey('online-form-record'), formId?: string) => request.post(`/online-forms/${encodeURIComponent(code)}/records/`, { data, ...(formId ? { form_id: formId } : {}) }, { headers: { 'Idempotency-Key': key } }),
  updateRecord: (code: string, id: string, data: Record<string, unknown>, version: number) => request.patch(`/online-forms/${encodeURIComponent(code)}/records/${id}/`, { data, version }),
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
  field_permissions?: Record<string, { read: string[]; write: string[] }>
  version: number
  id: string
  name: string
  description: string
  is_active: boolean
  permissions: Array<{ id: string; name: string; code: string }>
  created_at: string
}

export interface PermissionRow {
  id: string
  name: string
  code: string
  resource: string
  action: string
  description: string
  created_at: string
}

export interface MenuRow {
  version: number
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
  detail: async (id: string, signal?: AbortSignal): Promise<RoleRow> => (await request.get<ApiResponse<RoleRow>>(`/permissions/roles/${id}/`, { signal })).data.data,
  list: (params?: ListParams) => getPaged<RoleRow>('/permissions/roles/', params),
  create: (data: Partial<RoleRow> & { permission_ids?: string[] }) =>
    request.post('/permissions/roles/', data),
  update: (id: string, data: Partial<RoleRow> & { version: number; permission_ids?: string[] }) =>
    request.patch(`/permissions/roles/${id}/`, data),
  remove: (id: string) => request.delete(`/permissions/roles/${id}/`),
}

export const permissionsApi = {
  list: (params?: ListParams) => getPaged<PermissionRow>('/permissions/permissions/', params),
}

export const menusApi = {
  detail: async (id: string, signal?: AbortSignal): Promise<MenuRow> => (await request.get<ApiResponse<MenuRow>>(`/permissions/menus/${id}/`, { signal })).data.data,
  create: (data: Partial<MenuRow>) => request.post('/permissions/menus/', data),
  update: (id: string, data: Partial<MenuRow> & { version: number }) => request.patch(`/permissions/menus/${id}/`, data),
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
  actor_identifier?: string
  request_id?: string
  task_id?: string
  task_record_id?: string | null
  audit_version?: number
  before_values?: Record<string, unknown> | null
  after_values?: Record<string, unknown> | null
  batch_results?: Array<{ id: string; status: number }>
}

export interface LoginLogRow {
  id: string
  username: string
  status: 'success' | 'failed' | 'locked'
  ip_address: string
  error_message: string
  created_at: string
}

export interface ExceptionLogRow {
  id: string
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical'
  message: string
  username?: string | null
  ip_address?: string | null
  request_path: string
  request_method: string
  created_at: string
}

export const logsApi = {
  operation: (params?: ListParams) => getPaged<OperationLogRow>('/logs/operation/', params),
  operationDetail: async (id: string) => (await request.get<OperationLogRow>(`/logs/operation/${id}/`)).data,
  login: (params?: ListParams) => getPaged<LoginLogRow>('/logs/login/', params),
  exception: (params?: ListParams) => getPaged<ExceptionLogRow>('/logs/exception/', params),
}
