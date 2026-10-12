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

  const isAuthenticated = computed(() => !!token.value)

  async function login(username: string, password: string) {
    const data = await authApi.login(username, password)
    token.value = data.access
    refreshToken.value = data.refresh
    localStorage.setItem('token', data.access)
    localStorage.setItem('refreshToken', data.refresh)
    user.value = await authApi.me()
    return data.user
  }

  async function fetchUser() {
    if (!token.value) return null
    try {
      user.value = await authApi.me()
    } catch {
      // 拦截器已处理 401 跳转，这里仅吞掉异常
      user.value = null
    }
    return user.value
  }

  function clearSession() {
    token.value = ''
    refreshToken.value = ''
    user.value = null
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
