/**
 * 认证状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed, watch, onScopeDispose } from 'vue'
import authApi from '../api/auth'
import type { LoginResult } from '../api/auth'
import { tokensBelongToSameSession } from '../api/tokenRefresh'

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
  const token = ref<string>(localStorage.getItem('token') || '')
  const refreshToken = ref<string>(localStorage.getItem('refreshToken') || '')
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
    refreshToken.value = data.refresh
    localStorage.setItem('token', data.access)
    localStorage.setItem('refreshToken', data.refresh)
    user.value = data.user
    fetchedAt = Date.now()
  }
  function replaceSecuritySession(data: LoginResult, previousAccess: string | null) {
    if (!tokensBelongToSameSession(previousAccess, localStorage.getItem('token')) || data.user?.id !== user.value?.id || !data.access || !data.refresh) return false
    preservingSecuritySession.value = true
    try { installSession(data) } finally { preservingSecuritySession.value = false }
    return true
  }
  async function login(username: string, password: string, otpCode?: string) {
    const generation = ++sessionGeneration
    const data = await authApi.login(username, password, otpCode)
    if (generation !== sessionGeneration) throw new Error('Login session changed')
    preservingSecuritySession.value = true
    try { installSession(data) } finally { preservingSecuritySession.value = false }
    const installedGeneration = sessionGeneration
    const current = await authApi.me()
    if (installedGeneration !== sessionGeneration) throw new Error('Login session changed')
    user.value = current; fetchedAt = Date.now()
    return data.user
  }
  function cancelPendingLogin() { sessionGeneration++ }

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
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    window.dispatchEvent(new Event('admincore:session-cleared'))
  }

  function can(permission: string) {
    return !!user.value?.permissions?.some((code) => code === '*' || code === permission)
  }

  async function logout() {
    try {
      await authApi.logout()
    } finally {
      clearSession()
    }
  }

  return { token, refreshToken, user, isAuthenticated, login, fetchUser, logout, clearSession, can,
           avatarUrl, avatarLoading, avatarError, loadAvatar, avatarDecodeFailed, applyUser, replaceSecuritySession, preservingSecuritySession, cancelPendingLogin }
})
