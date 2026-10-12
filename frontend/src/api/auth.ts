/**
 * 认证相关 API
 */

import request, { type ApiResponse } from './request'
import type { CurrentUser } from '../stores/auth'

/** 登录响应（后端 CustomTokenObtainPair 为平铺结构） */
export interface LoginResult {
  access: string
  refresh: string
  user: CurrentUser
}

const authApi = {
  async login(username: string, password: string): Promise<LoginResult> {
    const res = await request.post('/auth/login/', { username, password })
    return res.data
  },

  async me(): Promise<CurrentUser> {
    const res = await request.get<ApiResponse<CurrentUser>>('/auth/me/')
    return res.data.data
  },

  async logout(): Promise<void> {
    await request.post('/auth/logout/')
  },

  async changePassword(oldPassword: string, newPassword: string, newPassword2: string): Promise<void> {
    await request.post('/auth/change_password/', {
      old_password: oldPassword,
      new_password: newPassword,
      new_password2: newPassword2,
    })
  },
}

export default authApi
