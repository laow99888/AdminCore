import request, { type ApiResponse } from './request'

export interface FieldDiagnosticInput {
  user_id: string
  resource: string
  field: string
  operation: 'read' | 'create' | 'update'
}
export interface FieldDiagnosticResult extends FieldDiagnosticInput {
  field_action: 'read' | 'write'
  field_allowed: boolean
  field_reason: 'administrator' | 'legacy_unrestricted' | 'explicit_union'
  permission_code: string | null
  operation_allowed: boolean
  user_active: boolean
  must_change_password: boolean
  module_enabled: boolean
  requires_admin: boolean
  tenant_id: string | null
  row_access: 'not_evaluated'
  roles: Array<{ id: string; name: string; version: number; active: boolean; declared: boolean; field_granted: boolean; operation_granted: boolean }>
  data_scope: Array<{ role_id: string; active: boolean; scope: string }>
}
export async function diagnoseField(input: FieldDiagnosticInput, signal?: AbortSignal): Promise<FieldDiagnosticResult> {
  return (await request.post<ApiResponse<FieldDiagnosticResult>>('/permissions/field-diagnostics/', input, { signal })).data.data
}
