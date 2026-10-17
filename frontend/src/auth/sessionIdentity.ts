/** 只比较已取得的令牌身份，不将未校验 JWT 用作服务端授权依据。 */
export function sessionClaims(token: string | null): { sid: string; user_id: string; session_version: number } | null {
  if (!token) return null
  try {
    const raw = token.split('.')[1]
    if (!raw) return null
    const value: unknown = JSON.parse(atob(raw.replace(/-/g, '+').replace(/_/g, '/')))
    if (!value || typeof value !== 'object') return null
    const claims = value as Record<string, unknown>
    if (typeof claims.sid !== 'string' || typeof claims.user_id !== 'string' || typeof claims.session_version !== 'number') return null
    return { sid: claims.sid, user_id: claims.user_id, session_version: claims.session_version }
  } catch { return null }
}

export function sessionIdentity(token: string | null): string | null {
  const claims = sessionClaims(token)
  return claims ? JSON.stringify([claims.sid, claims.user_id, claims.session_version]) : token
}

export function tokensBelongToSameSession(left: string | null, right: string | null): boolean {
  return !!left && !!right && sessionIdentity(left) === sessionIdentity(right)
}
