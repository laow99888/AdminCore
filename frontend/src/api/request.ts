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
import { refreshSessionTokens, tokensBelongToSameSession } from './tokenRefresh'
import { apiLanguage } from './language'
import publicRequest from './publicRequest'
import { API_BASE_URL } from './baseUrl'

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
  baseURL: API_BASE_URL,
  timeout: 30000,
})

// 请求拦截器：附加认证头
request.interceptors.request.use((config) => {
  config.headers['Accept-Language'] = apiLanguage()
  const token = localStorage.getItem('token')
  if ((config as any)._retried && !tokensBelongToSameSession((config as any)._sessionToken, token)) {
    // Re-login between refresh completion and dispatch must not replay prior work as the new actor.
    throw Object.assign(new Error('Session changed before retry'), { __CANCEL__: true })
  }
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
    if (!(config as any)._retried) (config as any)._sessionToken = token
  }
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

async function handle401(error: any): Promise<any> {
  const config = error.config
  const authorization = config?.headers?.Authorization
  const failedAccess = typeof authorization === 'string' ? authorization.replace(/^Bearer /, '') : localStorage.getItem('token')
  const originalAccess = config?._sessionToken ?? failedAccess
  const isAuthEndpoint = /\/auth\/(login|refresh)\//.test(config?.url || '')
  if (isAuthEndpoint || (config as any)?._retried) {
    // 登录/刷新本身的 401 由页面自行提示（登录页密码错误等）
    if (!isAuthEndpoint && config?.headers?.Authorization === `Bearer ${localStorage.getItem('token')}`) forceRelogin()
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
    if (!stale && tokensBelongToSameSession(originalAccess, localStorage.getItem('token'))) forceRelogin()
    return Promise.reject(error)
  }
  if (!tokensBelongToSameSession(originalAccess, access) || !tokensBelongToSameSession(originalAccess, localStorage.getItem('token'))) return Promise.reject(error)
  ;(config as any)._retried = true
  ;(config as any)._sessionToken = originalAccess
  config.headers = { ...config.headers, Authorization: `Bearer ${access}` }
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
