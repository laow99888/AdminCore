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

export interface PersonalProfile extends CurrentUser {
  first_name: string
  last_name: string
  phone: string
  bio: string
  profile_version: number
  has_avatar: boolean
  avatar_enabled: boolean
}
export type ProfileWrite = Pick<PersonalProfile, 'first_name' | 'last_name' | 'email' | 'phone' | 'bio' | 'profile_version'>

const authApi = {
  async profile(signal?: AbortSignal): Promise<PersonalProfile> {
    return (await request.get<ApiResponse<PersonalProfile>>('/auth/profile/', { signal })).data.data
  },
  async saveProfile(data: ProfileWrite): Promise<PersonalProfile> {
    return (await request.patch<ApiResponse<PersonalProfile>>('/auth/profile/', data)).data.data
  },
  async uploadAvatar(file: File, version: number): Promise<PersonalProfile> {
    const body = new FormData()
    body.append('file', file)
    body.append('profile_version', String(version))
    return (await request.post<ApiResponse<PersonalProfile>>('/auth/avatar/', body)).data.data
  },
  async removeAvatar(version: number): Promise<PersonalProfile> {
    return (await request.delete<ApiResponse<PersonalProfile>>('/auth/avatar/', { data: { profile_version: version } })).data.data
  },
  async avatar(signal: AbortSignal): Promise<Blob> {
    const blob = (await request.get<Blob>('/auth/avatar/', { responseType: 'blob', signal })).data
    if (blob.type !== 'image/png' || blob.size > 1024 * 1024 || blob.size === 0) throw new Error('Invalid avatar response')
    return blob
  },
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
