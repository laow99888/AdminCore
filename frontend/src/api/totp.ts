import request, { type ApiResponse } from './request'
import type { LoginResult } from './auth'

export interface TotpStatus { enabled: boolean; available: boolean; recovery_codes_remaining: number }
export interface TotpSetup { secret: string; otpauth_uri: string; expires_at: string }
export interface TotpSession extends LoginResult { recovery_codes?: string[] }
export const totpApi = {
  status: async (signal?: AbortSignal) => (await request.get<ApiResponse<TotpStatus>>('/auth/totp/', { signal })).data.data,
  setup: async (currentPassword: string) => (await request.post<ApiResponse<TotpSetup>>('/auth/totp/setup/', { current_password: currentPassword })).data.data,
  enable: async (currentPassword: string, otpCode: string) => (await request.post<ApiResponse<TotpSession>>('/auth/totp/enable/', { current_password: currentPassword, otp_code: otpCode })).data.data,
  disable: async (currentPassword: string, otpCode: string) => (await request.post<ApiResponse<TotpSession>>('/auth/totp/disable/', { current_password: currentPassword, otp_code: otpCode })).data.data,
  regenerate: async (currentPassword: string, otpCode: string) => (await request.post<ApiResponse<TotpSession>>('/auth/totp/recovery-codes/', { current_password: currentPassword, otp_code: otpCode })).data.data,
}
