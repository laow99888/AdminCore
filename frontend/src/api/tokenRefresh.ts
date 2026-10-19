interface RefreshResult { access: string | null; stale: boolean; retryable?: boolean }
import { retryableRefresh } from '../auth/refreshFailure'
type RefreshRequest = (refresh: string) => Promise<{ access?: unknown; refresh?: unknown }>
import { getAccessToken, getRefreshToken, setAccessToken, setRefreshToken } from '../auth/tokenStorage'
import { sessionIdentity as identity } from '../auth/sessionIdentity'
export { tokensBelongToSameSession } from '../auth/sessionIdentity'

/** Serialize single-use refresh rotation across tabs without replaying old work as a new login. */
export async function refreshSessionTokens(failedAccess: string | null, post: RefreshRequest): Promise<RefreshResult> {
  const initialRefresh = getRefreshToken()
  const initialAccess = getAccessToken()
  if (!initialRefresh || !initialAccess) return { access: null, stale: !initialAccess }
  const originalIdentity = identity(failedAccess) ?? identity(initialAccess) ?? identity(initialRefresh)
  const sameSession = (access: string | null, refresh: string | null) => !!access && !!refresh &&
    (originalIdentity ? identity(access) === originalIdentity : refresh === initialRefresh)
  const run = async (): Promise<RefreshResult> => {
    const refresh = getRefreshToken(), access = getAccessToken()
    if (!sameSession(access, refresh)) return { access: null, stale: true }
    // Another tab may already have rotated while this request waited for the origin lock.
    if (access !== failedAccess) return { access, stale: false }
    try {
      const tokens = await post(refresh!)
      const latestAccess = getAccessToken(), latestRefresh = getRefreshToken()
      if (latestRefresh !== refresh || latestAccess !== access) {
        return sameSession(latestAccess, latestRefresh) && latestAccess !== failedAccess ? { access: latestAccess, stale: false } : { access: null, stale: true }
      }
      if (typeof tokens.access !== 'string' || !tokens.access) return { access: null, stale: false }
      setAccessToken(tokens.access)
      if (typeof tokens.refresh === 'string' && tokens.refresh) setRefreshToken(tokens.refresh)
      return { access: tokens.access, stale: false }
    } catch (error) {
      const latestAccess = getAccessToken(), latestRefresh = getRefreshToken()
      // Fallback for browsers without Web Locks: reuse a rotation completed by another tab.
      if (sameSession(latestAccess, latestRefresh) && latestAccess !== failedAccess) return { access: latestAccess, stale: false }
      const stale = latestRefresh !== refresh || latestAccess !== access
      return { access: null, stale, ...(!stale && retryableRefresh(error) ? { retryable: true } : {}) }
    }
  }
  return navigator.locks?.request ? navigator.locks.request('admincore:refresh-token', run) : run()
}
