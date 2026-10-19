import publicRequest from '../api/publicRequest'
import { retryableRefresh } from './refreshFailure'
import { API_BASE_URL } from '../api/baseUrl'
import { cookieSessionEnabled, BROWSER_SESSION_MARKER, MEMORY_TOKEN_CHANGED } from './sessionTransport'
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, announceBrowserSession, browserSessionMarker, clearLegacyTokens, clearSession, discardMemorySession, getAccessToken, setAccessToken } from './tokenStorage'
import { sessionClaims, tokensBelongToSameSession } from './sessionIdentity'

const ENDPOINT = '/auth/browser-session/'
const LOCK = 'admincore:refresh-token'

/** 所有会改写同源 Cookie 的操作共用一个锁；不支持时失败，不静默降级。 */
export async function withBrowserSessionLock<T>(run: () => Promise<T>): Promise<T> {
  if (!cookieSessionEnabled()) return run()
  const base = new URL(API_BASE_URL, window.location.origin)
  if (base.origin !== window.location.origin || base.username || base.password || base.search || base.hash ||
      base.pathname.replace(/\/+$/, '') !== '/api/v1' || !navigator.locks?.request) {
    return Promise.reject(new Error('Cookie sessions require a same-origin API and Web Locks'))
  }
  const marker = browserSessionMarker()
  return await navigator.locks.request(LOCK, async () => {
    if (marker !== browserSessionMarker()) throw new Error('Browser session changed while waiting')
    return run()
  })
}

export async function browserSessionHeaders(): Promise<Record<string, string>> {
  if (!cookieSessionEnabled()) return {}
  const result = await publicRequest.get<{ data: { csrf_token: string } }>(ENDPOINT)
  const csrf = result.data?.data?.csrf_token
  if (typeof csrf !== 'string' || !csrf) throw new Error('Missing browser CSRF proof')
  return { 'X-AdminCore-Session': 'cookie', 'X-CSRFToken': csrf }
}

export function validateBrowserSession<T extends { access: string; refresh?: string; session_transport?: 'cookie' }>(value: T): T {
  if (cookieSessionEnabled() && (value.session_transport !== 'cookie' || value.refresh !== undefined || !sessionClaims(value.access))) {
    throw new Error('Cookie session negotiation failed')
  }
  return value
}

/** 必须在锁内执行，且必须在请求前及安装前验证世代。 */
export async function restoreBrowserSession(expected: string | null): Promise<string> {
  const marker = browserSessionMarker()
  const headers = await browserSessionHeaders()
  const claims = sessionClaims(expected)
  if (expected && !claims) throw new Error('Invalid browser session identity')
  if (marker !== browserSessionMarker() || expected !== getAccessToken()) throw new Error('Browser session changed')
  const result = await publicRequest.post<{ data: { access: string; session_transport?: 'cookie'; refresh?: string } }>(
    ENDPOINT, claims ? { session_id: claims.sid } : {}, { headers })
  const value = validateBrowserSession(result.data.data)
  if (marker !== browserSessionMarker() || expected !== getAccessToken() ||
      (expected && !tokensBelongToSameSession(expected, value.access))) throw new Error('Browser session changed')
  if (!marker) announceBrowserSession('active')
  setAccessToken(value.access)
  return value.access
}

export async function initializeBrowserSession(): Promise<void> {
  if (!cookieSessionEnabled()) return
  clearLegacyTokens()
  await withBrowserSessionLock(async () => {
    const marker = browserSessionMarker()
    if (marker) {
      let state: unknown
      try { state = JSON.parse(marker) } catch { throw new Error('Invalid browser session marker') }
      if (!state || typeof state !== 'object' || !('state' in state) || !('epoch' in state) ||
          typeof state.epoch !== 'string' || !['active', 'signed_out'].includes(String(state.state))) throw new Error('Invalid browser session marker')
      if (state.state === 'signed_out') return
    }
    try { await restoreBrowserSession(null) }
    catch (error: unknown) {
      const status = (error as { response?: { status?: number } })?.response?.status
      if (status !== 401) throw error
      // 不向其它标签广播；初始恢复失败不应清除它们稍后建立的会话。
      discardMemorySession()
    }
  })
}

export async function refreshBrowserSession(failed: string | null): Promise<{ access: string | null; stale: boolean; retryable?: boolean }> {
  const marker = browserSessionMarker()
  try {
    return await withBrowserSessionLock(async () => {
      const current = getAccessToken()
      if (!tokensBelongToSameSession(failed, current) || marker !== browserSessionMarker()) return { access: null, stale: true }
      if (current !== failed) return { access: current, stale: false }
      return { access: await restoreBrowserSession(current), stale: false }
    })
  } catch (error) {
    const stale = marker !== browserSessionMarker() || !tokensBelongToSameSession(failed, getAccessToken())
    return { access: null, stale, ...(!stale && retryableRefresh(error) ? { retryable: true } : {}) }
  }
}

/** 调用者持锁，并在 finally 中清空本地状态；退出不会触发 access 自动刷新。 */
export async function logoutBrowserSession(access = getAccessToken()): Promise<void> {
  const claims = sessionClaims(access)
  if (!claims) return
  const headers = await browserSessionHeaders()
  await publicRequest.delete(ENDPOINT, { headers, data: { session_id: claims.sid } })
}

/** 登录响应到达时页面已取消：撤销已写入 Cookie 的新会话，禁止下次加载悄悄恢复。 */
export async function discardCancelledBrowserLogin(access: string): Promise<void> {
  if (!cookieSessionEnabled()) return
  try { await logoutBrowserSession(access) }
  finally { clearSession() }
}

export function startBrowserSessionSync(onChange: () => void): () => void {
  const marker = () => cookieSessionEnabled() ? browserSessionMarker() : getAccessToken()
  let known = marker()
  const ownChange = () => { known = marker() }
  const check = () => {
    const next = marker()
    if (known === next) return
    const same = !cookieSessionEnabled() && tokensBelongToSameSession(known, next)
    known = next
    if (same) { window.dispatchEvent(new Event(MEMORY_TOKEN_CHANGED)); return }
    if (cookieSessionEnabled()) discardMemorySession()
    else window.dispatchEvent(new Event(MEMORY_TOKEN_CHANGED))
    onChange()
  }
  const storage = (event: StorageEvent) => { if (event.key === null ||
    (cookieSessionEnabled() ? event.key === BROWSER_SESSION_MARKER : [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY].includes(event.key))) check() }
  window.addEventListener('storage', storage)
  window.addEventListener('focus', check)
  document.addEventListener('visibilitychange', check)
  window.addEventListener(MEMORY_TOKEN_CHANGED, ownChange)
  return () => {
    window.removeEventListener('storage', storage); window.removeEventListener('focus', check)
    document.removeEventListener('visibilitychange', check); window.removeEventListener(MEMORY_TOKEN_CHANGED, ownChange)
  }
}
