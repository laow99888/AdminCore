import axios from 'axios'
import type { ApiResponse } from './request'

// Public recovery never attaches a stored JWT or enters the authenticated refresh flow.
const publicRequest = axios.create({ baseURL: (import.meta.env.VITE_API_BASE_URL as string) || '/api/v1', timeout: 30000 })
export function passwordResetError(reason: unknown): string | undefined {
  const response = (reason as { response?: { status?: number; data?: { data?: Record<string, unknown> } } })?.response
  if (response?.status !== 400) return undefined
  for (const field of ['new_password', 'new_password2']) {
    const value = response.data?.data?.[field]
    const message = Array.isArray(value) ? value[0] : value
    if (typeof message === 'string' && message.length > 0 && message.length <= 500) return message
  }
  return undefined
}
export const recoveryApi = {
  async config(signal?: AbortSignal): Promise<{ enabled: boolean }> {
    const data = (await publicRequest.get<ApiResponse<{ enabled: boolean }>>('/auth/recovery/config/', { signal })).data.data
    if (typeof data?.enabled !== 'boolean') throw new Error('Invalid recovery configuration')
    return data
  },
  async request(username: string, email: string): Promise<void> {
    await publicRequest.post('/auth/recovery/request/', { username, email })
  },
  async reset(code: string, newPassword: string, newPassword2: string): Promise<void> {
    await publicRequest.post('/auth/recovery/reset/', { code, new_password: newPassword, new_password2: newPassword2 })
  },
}
