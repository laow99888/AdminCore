/**
 * 认证状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import authApi from '../api/auth'

export interface CurrentUser {
  id: string
  username: string
  email: string
  avatar: string
  is_staff?: boolean
  is_superuser?: boolean
  permissions?: string[]
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const refreshToken = ref<string>(localStorage.getItem('refreshToken') || '')
  const user = ref<CurrentUser | null>(null)
  let fetchedAt = 0
  let fetching: Promise<CurrentUser | null> | undefined
  let sessionGeneration = 0

  const isAuthenticated = computed(() => !!token.value)

  async function login(username: string, password: string) {
    sessionGeneration++
    const data = await authApi.login(username, password)
    token.value = data.access
    refreshToken.value = data.refresh
    localStorage.setItem('token', data.access)
    localStorage.setItem('refreshToken', data.refresh)
    user.value = await authApi.me()
    fetchedAt = Date.now()
    return data.user
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
    sessionGeneration++
    fetching = undefined
    token.value = ''
    refreshToken.value = ''
    user.value = null
    fetchedAt = 0
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
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

  return { token, refreshToken, user, isAuthenticated, login, fetchUser, logout, clearSession, can }
})
