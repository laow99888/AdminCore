/**
 * 认证令牌存储适配器。
 *
 * 默认兼容既有 localStorage；显式 Cookie 模式只保留内存 access，清除旧持久化凭据。
 * 跨标签只同步无凭据的随机会话标记，事件不携带 access/refresh。
 */
import { cookieSessionEnabled, BROWSER_SESSION_MARKER, MEMORY_TOKEN_CHANGED } from './sessionTransport'

export const ACCESS_TOKEN_KEY = 'token'
export const REFRESH_TOKEN_KEY = 'refreshToken'

export interface StoredSession {
  access: string
  refresh?: string
  session_transport?: 'cookie'
}

let memoryAccess: string | null = null
const changed = () => window.dispatchEvent(new Event(MEMORY_TOKEN_CHANGED))

export function browserSessionMarker(): string | null { return storage()?.getItem(BROWSER_SESSION_MARKER) ?? null }

export function announceBrowserSession(state: 'active' | 'signed_out'): void {
  storage()?.setItem(BROWSER_SESSION_MARKER, JSON.stringify({ state, epoch: crypto.randomUUID() }))
}

export function clearLegacyTokens(): void {
  storage()?.removeItem(ACCESS_TOKEN_KEY)
  storage()?.removeItem(REFRESH_TOKEN_KEY)
}

/** 仅丢弃本标签内存，避免在处理其他标签信号时向它反向广播。 */
export function discardMemorySession(): void { memoryAccess = null; changed() }

function storage(): Storage | undefined {
  if (typeof localStorage === 'undefined') return undefined
  return localStorage
}

export function getAccessToken(): string | null {
  if (cookieSessionEnabled()) return memoryAccess
  return storage()?.getItem(ACCESS_TOKEN_KEY) ?? null
}

export function getRefreshToken(): string | null {
  if (cookieSessionEnabled()) return null
  return storage()?.getItem(REFRESH_TOKEN_KEY) ?? null
}

export function setAccessToken(value: string): void {
  if (cookieSessionEnabled()) { clearLegacyTokens(); memoryAccess = value; changed(); return }
  storage()?.setItem(ACCESS_TOKEN_KEY, value)
  changed()
}

export function setRefreshToken(value: string): void {
  if (cookieSessionEnabled()) throw new Error('Cookie sessions cannot store refresh credentials')
  storage()?.setItem(REFRESH_TOKEN_KEY, value)
}

export function setSession(session: StoredSession): void {
  if (cookieSessionEnabled()) {
    if (session.session_transport !== 'cookie' || session.refresh !== undefined) throw new Error('Cookie session negotiation failed')
    clearLegacyTokens(); announceBrowserSession('active'); memoryAccess = session.access; changed(); return
  }
  if (!session.refresh) throw new Error('Missing refresh credential')
  const target = storage()
  if (!target) return
  target.setItem(ACCESS_TOKEN_KEY, session.access)
  target.setItem(REFRESH_TOKEN_KEY, session.refresh)
  changed()
}

export function clearSession(): void {
  if (cookieSessionEnabled()) { clearLegacyTokens(); announceBrowserSession('signed_out'); discardMemorySession(); return }
  const target = storage()
  if (!target) return
  target.removeItem(ACCESS_TOKEN_KEY)
  target.removeItem(REFRESH_TOKEN_KEY)
  changed()
}

export function getSessionSnapshot(): { access: string | null; refresh: string | null } {
  return { access: getAccessToken(), refresh: getRefreshToken() }
}
