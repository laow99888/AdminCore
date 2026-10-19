/** 租户选择属于当前标签页；不能由其他标签的共享偏好静默改写。 */
const KEY = 'admincore.tenant'

export function getTenantId(): string {
  try { return sessionStorage.getItem(KEY) || '' } catch { return '' }
}

export function setTenantId(id: string): void {
  if (id) sessionStorage.setItem(KEY, id)
  else sessionStorage.removeItem(KEY)
  // 旧版本共享选择不再作为请求依据。
  localStorage.removeItem(KEY)
}
