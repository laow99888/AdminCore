import { uiText } from "@/i18n/uiText"
/**
 * Axios 请求封装
 * - 自动携带 JWT（localStorage.token）
 * - 401 自动用 refreshToken 刷新并重放原请求（access 有效期仅 5 分钟）
 * - 刷新失败才清除凭证并跳转登录页
 * - 统一错误提示（后端约定响应格式 {code, message, data}）
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { useAuthStore } from '../stores/auth'

export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

export interface Pagination {
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PagedData<T = any> {
  items: T[]
  pagination: Pagination
}

const request = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL as string) || '/api/v1',
  timeout: 30000,
})

// 请求拦截器：附加认证头
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ---- access token 自动刷新（access 有效期仅 5 分钟）----
let refreshing: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('refreshToken')
  if (!refreshToken) return null
  try {
    // 用裸 axios：不带过期的 access，也不走本实例拦截器避免递归
    const res = await axios.post(`${request.defaults.baseURL}/auth/refresh/`, {
      refresh: refreshToken,
    })
    const body = res.data
    const access = body?.data?.access ?? body?.access
    if (!access) return null
    localStorage.setItem('token', access)
    const rotatedRefresh = body?.data?.refresh ?? body?.refresh
    if (rotatedRefresh) localStorage.setItem('refreshToken', rotatedRefresh)
    return access
  } catch {
    return null
  }
}

function forceRelogin() {
  useAuthStore().clearSession()
  if (router.currentRoute.value.path !== '/login') {
    ElMessage.error(uiText("登录已过期，请重新登录"))
    router.push('/login')
  }
}

async function handle401(error: any): Promise<any> {
  const config = error.config
  const isAuthEndpoint = /\/auth\/(login|refresh)\//.test(config?.url || '')
  if (isAuthEndpoint || (config as any)?._retried) {
    // 登录/刷新本身的 401 由页面自行提示（登录页密码错误等）
    if (!isAuthEndpoint) forceRelogin()
    return Promise.reject(error)
  }
  // 并发 401 只触发一次刷新，其余等待同一 Promise
  if (!refreshing) {
    refreshing = refreshAccessToken().finally(() => {
      refreshing = null
    })
  }
  const access = await refreshing
  if (!access) {
    forceRelogin()
    return Promise.reject(error)
  }
  ;(config as any)._retried = true
  config.headers = { ...config.headers, Authorization: `Bearer ${access}` }
  return request(config)
}

// 响应拦截器：统一错误处理；401 自动刷新并重放原请求
request.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isCancel(error)) return Promise.reject(error)
    if (error.response) {
      const { status } = error.response
      if (status === 401) {
        return handle401(error)
      }
      const { data } = error.response
      if (status === 403 && data?.data?.reason === 'password_change_required') {
        if (router.currentRoute.value.path !== '/change-password') router.replace('/change-password')
        return Promise.reject(error)
      }
      // 后端统一错误格式 {code, message, data}
      const message = (data && data.message) || uiText("请求失败（{p0}）", { p0: status })
      ElMessage.error(status === 403 ? uiText("没有执行此操作的权限") : message)
    } else {
      ElMessage.error(uiText("网络异常，请检查连接"))
    }
    return Promise.reject(error)
  }
)

export default request
