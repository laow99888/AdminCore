import { uiText } from "@/i18n/uiText"
/**
 * Axios 请求封装
 * - 自动携带 JWT（由认证令牌存储适配器提供）
 * - 401 自动用 refreshToken 刷新并重放原请求（access 有效期仅 5 分钟）
 * - 刷新失败才清除凭证并跳转登录页
 * - 统一错误提示（后端约定响应格式 {code, message, data}）
 */

import axios, { type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { useAuthStore } from '../stores/auth'
import { refreshSessionTokens, tokensBelongToSameSession } from './tokenRefresh'
import { apiLanguage } from './language'
import publicRequest from './publicRequest'
import { API_BASE_URL } from './baseUrl'
import { getAccessToken } from '../auth/tokenStorage'

declare module 'axios' {
  interface InternalAxiosRequestConfig {
    _retried?: boolean
    _sessionToken?: string | null
  }
}

export interface ApiResponse<T = unknown> {
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

export interface PagedData<T = unknown> {
  items: T[]
  pagination: Pagination
}

/** 从未知异常中提取可展示的固定消息，避免业务组件把 catch 值当作 any。 */
export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'string' && error) return error
  if (axios.isAxiosError(error)) {
    const data: unknown = error.response?.data
    if (data && typeof data === 'object' && 'message' in data && typeof data.message === 'string' && data.message) {
      return data.message
    }
  }
  return fallback
}

/** 从未知异常中提取 HTTP 状态，供业务组件处理冲突等明确分支。 */
export function responseStatus(error: unknown): number | undefined {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  const response: unknown = error.response
  return response && typeof response === 'object' && 'status' in response && typeof response.status === 'number' ? response.status : undefined
}

const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
})

// 请求拦截器：附加认证头
request.interceptors.request.use((config) => {
  config.headers['Accept-Language'] = apiLanguage()
  const token = getAccessToken()
  if (config._retried && !tokensBelongToSameSession(config._sessionToken ?? null, token)) {
    // Re-login between refresh completion and dispatch must not replay prior work as the new actor.
    throw Object.assign(new Error('Session changed before retry'), { __CANCEL__: true })
  }
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
    if (!config._retried) config._sessionToken = token
  }
  const tenant = localStorage.getItem('admincore.tenant')
  if (tenant) config.headers['X-AdminCore-Tenant'] = tenant
  return config
})

// ---- access token 自动刷新（access 有效期仅 5 分钟）----
let refreshing: ReturnType<typeof refreshSessionTokens> | null = null
let refreshingToken: string | null = null

function refreshAccessToken(failedAccess: string | null) {
  return refreshSessionTokens(failedAccess, async refreshToken => {
    // 独立公开传输只携带当前语言，不带过期 access、不递归刷新，并限制超时。
    const res = await publicRequest.post('/auth/refresh/', {
      refresh: refreshToken,
    })
    const body = res.data
    return { access: body?.data?.access ?? body?.access, refresh: body?.data?.refresh ?? body?.refresh }
  })
}

function forceRelogin() {
  useAuthStore().clearSession()
  if (router.currentRoute.value.path !== '/login') {
    ElMessage.error(uiText("登录已过期，请重新登录"))
    router.push('/login')
  }
}

async function handle401(error: AxiosError): Promise<unknown> {
  const config = error.config
  if (!config) return Promise.reject(error)
  const authorization = config?.headers?.Authorization
  const failedAccess = typeof authorization === 'string' ? authorization.replace(/^Bearer /, '') : getAccessToken()
  const originalAccess = config?._sessionToken ?? failedAccess
  const isAuthEndpoint = /\/auth\/(login|refresh)\//.test(config?.url || '')
  if (isAuthEndpoint || config?._retried) {
    // 登录/刷新本身的 401 由页面自行提示（登录页密码错误等）
    if (!isAuthEndpoint && config?.headers?.Authorization === `Bearer ${getAccessToken()}`) forceRelogin()
    return Promise.reject(error)
  }
  // 并发 401 只触发一次刷新，其余等待同一 Promise
  if (!refreshing || !tokensBelongToSameSession(refreshingToken, originalAccess)) {
    const pending = refreshAccessToken(failedAccess).finally(() => {
      if (refreshing === pending) { refreshing = null; refreshingToken = null }
    })
    refreshing = pending
    refreshingToken = originalAccess
  }
  const { access, stale } = await refreshing
  if (!access) {
    if (!stale && tokensBelongToSameSession(originalAccess, getAccessToken())) forceRelogin()
    return Promise.reject(error)
  }
  if (!tokensBelongToSameSession(originalAccess, access) || !tokensBelongToSameSession(originalAccess, getAccessToken())) return Promise.reject(error)
  config._retried = true
  config._sessionToken = originalAccess
  config.headers.Authorization = `Bearer ${access}`
  return request(config)
}

// 响应拦截器：统一错误处理；401 自动刷新并重放原请求
request.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isCancel(error)) return Promise.reject(error)
    // The login page owns credential, captcha, MFA, throttling and network feedback.
    if (/\/auth\/login\/(?:\?|$)/.test(error.config?.url || '')) return Promise.reject(error)
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
