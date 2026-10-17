/**
 * 认证状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed, watch, onScopeDispose } from 'vue'
import authApi from '../api/auth'
import type { LoginResult } from '../api/auth'
import { tokensBelongToSameSession } from '../api/tokenRefresh'
import { announceBrowserSession, clearSession as clearStoredSession, getAccessToken, getRefreshToken, setSession as setStoredSession } from '../auth/tokenStorage'
import { cookieSessionEnabled, MEMORY_TOKEN_CHANGED } from '../auth/sessionTransport'
import { withBrowserSessionLock, discardCancelledBrowserLogin } from '../auth/browserSession'

export interface CurrentUser {
  id: string
  username: string
  email: string
  avatar: string
  is_staff?: boolean
  is_superuser?: boolean
  permissions?: string[]
  must_change_password?: boolean
  profile_version?: number
  has_avatar?: boolean
  avatar_enabled?: boolean
  email_verified?: boolean
  recovery_enabled?: boolean
  totp_enabled?: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(getAccessToken() || '')
  const refreshToken = ref<string>(getRefreshToken() || '')
  const user = ref<CurrentUser | null>(null)
  const avatarUrl = ref('')
  const avatarLoading = ref(false)
  const avatarError = ref(false)
  const preservingSecuritySession = ref(false)
  let avatarRequest: AbortController | undefined
  let avatarGeneration = 0
  let fetchedAt = 0
  let fetching: Promise<CurrentUser | null> | undefined
  let sessionGeneration = 0

  const isAuthenticated = computed(() => !!token.value)

  function clearAvatar() {
    avatarGeneration++
    avatarRequest?.abort()
    avatarRequest = undefined
    if (avatarUrl.value) URL.revokeObjectURL(avatarUrl.value)
    avatarUrl.value = ''
    avatarLoading.value = false
    avatarError.value = false
  }

  async function loadAvatar() {
    clearAvatar()
    if (!token.value || !user.value?.has_avatar || !user.value.avatar_enabled || user.value.must_change_password) return
    const generation = avatarGeneration
    const controller = new AbortController()
    avatarRequest = controller
    avatarLoading.value = true
    try {
      const blob = await authApi.avatar(controller.signal)
      if (generation === avatarGeneration) avatarUrl.value = URL.createObjectURL(blob)
    } catch {
      if (generation === avatarGeneration && !controller.signal.aborted) avatarError.value = true
    } finally {
      if (generation === avatarGeneration) { avatarLoading.value = false; avatarRequest = undefined }
    }
  }

  function avatarDecodeFailed() {
    clearAvatar()
    avatarError.value = true
  }

  watch([() => user.value?.id, () => user.value?.profile_version, () => user.value?.has_avatar,
         () => user.value?.avatar_enabled, () => user.value?.must_change_password], loadAvatar)
  onScopeDispose(clearAvatar)

  function applyUser(value: CurrentUser) {
    sessionGeneration++
    fetching = undefined
    user.value = value
    fetchedAt = Date.now()
  }

  function installSession(data: LoginResult) {
    sessionGeneration++; fetching = undefined
    token.value = data.access
    refreshToken.value = data.refresh ?? ''
    setStoredSession(data)
    user.value = data.user
    fetchedAt = Date.now()
  }
  function replaceSecuritySession(data: LoginResult, previousAccess: string | null) {
    if (!tokensBelongToSameSession(previousAccess, getAccessToken()) || data.user?.id !== user.value?.id || !data.access ||
        (cookieSessionEnabled() ? data.session_transport !== 'cookie' : !data.refresh)) return false
    preservingSecuritySession.value = true
    try { installSession(data) } finally { preservingSecuritySession.value = false }
    return true
  }
  async function login(username: string, password: string, otpCode?: string, captcha?: import('../api/loginCaptcha').LoginCaptchaProof) {
    const generation = ++sessionGeneration
    const data = await withBrowserSessionLock(async () => {
      if (generation !== sessionGeneration) throw new Error('Login session changed')
      const value = await authApi.login(username, password, otpCode, captcha).catch(error => {
        if (cookieSessionEnabled()) announceBrowserSession('signed_out')
        throw error
      })
      if (generation !== sessionGeneration) {
        await discardCancelledBrowserLogin(value.access)
        throw new Error('Login session changed')
      }
      preservingSecuritySession.value = true
      try { installSession(value) } finally { preservingSecuritySession.value = false }
      return value
    })
    const installedGeneration = sessionGeneration
    const current = await authApi.me()
    if (installedGeneration !== sessionGeneration) throw new Error('Login session changed')
    // me返回更完整的权限/账户字段；仍属于同一次登录，不能卸载等待导航的登录页。
    preservingSecuritySession.value = true
    try { user.value = current; fetchedAt = Date.now() } finally { preservingSecuritySession.value = false }
    return data.user
  }
  function cancelPendingLogin() {
    sessionGeneration++
    if (cookieSessionEnabled() && !getAccessToken()) announceBrowserSession('signed_out')
  }

  async function loginSSO(proof: import('../api/sso').SSOLocalProof, signal?: AbortSignal) {
    if (__ADMINCORE_MINIMAL_BUILD__) throw new Error('Enterprise sign-in is unavailable in this build')
    else {
      if (token.value || getAccessToken()) throw new Error('Already signed in')
      const generation = ++sessionGeneration
      const { ssoApi } = await import('../api/sso')
      if (generation !== sessionGeneration || signal?.aborted) throw new Error('Login session changed')
      const data = await withBrowserSessionLock(async () => {
        if (generation !== sessionGeneration || signal?.aborted || getAccessToken()) throw new Error('Login session changed')
        const value = await ssoApi.complete(proof, signal).catch(error => {
          if (cookieSessionEnabled()) announceBrowserSession('signed_out')
          throw error
        })
        if (generation !== sessionGeneration || signal?.aborted || getAccessToken()) {
          await discardCancelledBrowserLogin(value.access)
          throw new Error('Login session changed')
        }
        preservingSecuritySession.value = true
        try { installSession(value) } finally { preservingSecuritySession.value = false }
        return value
      })
      const installedGeneration = sessionGeneration
      const current = await authApi.me()
      if (installedGeneration !== sessionGeneration) throw new Error('Login session changed')
      preservingSecuritySession.value = true
      try { user.value = current; fetchedAt = Date.now() } finally { preservingSecuritySession.value = false }
      return data.user
    }
  }

  async function fetchUser(force = false) {
    if (!token.value) return null
    if (!force && user.value && Date.now() - fetchedAt < 30000) return user.value
    if (!fetching) {
      const generation = sessionGeneration
      const active = authApi.me().then(value => {
        if (generation !== sessionGeneration) return user.value
        user.value = value; fetchedAt = Date.now(); return value
      }).catch(() => { if (generation === sessionGeneration) user.value = null; return null })
        .finally(() => { if (fetching === active) fetching = undefined })
      fetching = active
    }
    return fetching
  }

  function clearSession() {
    clearAvatar()
    sessionGeneration++
    fetching = undefined
    token.value = ''
    refreshToken.value = ''
    user.value = null
    fetchedAt = 0
    clearStoredSession()
    window.dispatchEvent(new Event('admincore:session-cleared'))
  }

  function can(permission: string) {
    return !!user.value?.permissions?.some((code) => code === '*' || code === permission)
  }

  async function logout() {
    const owner = getAccessToken()
    await withBrowserSessionLock(async () => {
      if (cookieSessionEnabled() && !tokensBelongToSameSession(owner, getAccessToken())) return
      try { await authApi.logout() }
      finally { if (!cookieSessionEnabled() || tokensBelongToSameSession(owner, getAccessToken())) clearSession() }
    })
  }

  const memoryChanged = () => {
    if (!cookieSessionEnabled()) return
    const access = getAccessToken()
    if (!tokensBelongToSameSession(token.value, access)) {
      sessionGeneration++; fetching = undefined; user.value = null; fetchedAt = 0; clearAvatar()
    }
    token.value = access ?? ''
    refreshToken.value = ''
  }
  window.addEventListener(MEMORY_TOKEN_CHANGED, memoryChanged)
  onScopeDispose(() => window.removeEventListener(MEMORY_TOKEN_CHANGED, memoryChanged))

  return { token, refreshToken, user, isAuthenticated, login, loginSSO, fetchUser, logout, clearSession, can,
           avatarUrl, avatarLoading, avatarError, loadAvatar, avatarDecodeFailed, applyUser, replaceSecuritySession, preservingSecuritySession, cancelPendingLogin }
})
