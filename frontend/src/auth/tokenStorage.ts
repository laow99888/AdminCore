/**
 * 认证令牌存储适配器。
 *
 * 当前实现保持既有 localStorage 键名，以兼容旧客户端、刷新流程和多标签页。
 * 令牌不应进入 URL、日志或事件负载；未来迁移到 HttpOnly/BFF 时，只替换本适配器及其
 * 会话同步实现，业务代码不再直接依赖存储介质。
 */

export const ACCESS_TOKEN_KEY = 'token'
export const REFRESH_TOKEN_KEY = 'refreshToken'

export interface StoredSession {
  access: string
  refresh: string
}

function storage(): Storage | undefined {
  if (typeof localStorage === 'undefined') return undefined
  return localStorage
}

export function getAccessToken(): string | null {
  return storage()?.getItem(ACCESS_TOKEN_KEY) ?? null
}

export function getRefreshToken(): string | null {
  return storage()?.getItem(REFRESH_TOKEN_KEY) ?? null
}

export function setAccessToken(value: string): void {
  storage()?.setItem(ACCESS_TOKEN_KEY, value)
}

export function setRefreshToken(value: string): void {
  storage()?.setItem(REFRESH_TOKEN_KEY, value)
}

export function setSession(session: StoredSession): void {
  const target = storage()
  if (!target) return
  target.setItem(ACCESS_TOKEN_KEY, session.access)
  target.setItem(REFRESH_TOKEN_KEY, session.refresh)
}

export function clearSession(): void {
  const target = storage()
  if (!target) return
  target.removeItem(ACCESS_TOKEN_KEY)
  target.removeItem(REFRESH_TOKEN_KEY)
}

export function getSessionSnapshot(): { access: string | null; refresh: string | null } {
  return { access: getAccessToken(), refresh: getRefreshToken() }
}
