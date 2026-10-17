import request, { type ApiResponse } from './request'
import type { LoginResult } from './auth'
import { browserSessionHeaders, validateBrowserSession } from '../auth/browserSession'
import { cookieSessionEnabled } from '../auth/sessionTransport'

async function change(operation: string, currentPassword: string, otpCode: string): Promise<TotpSession> {
  const headers = await browserSessionHeaders()
  const path = '/auth/totp/' + operation + '/', body = { current_password: currentPassword, otp_code: otpCode }
  const result = cookieSessionEnabled() ? await request.post<ApiResponse<TotpSession>>(path, body, { headers, _skipAuthRefresh: true }) :
    await request.post<ApiResponse<TotpSession>>(path, body)
  return validateBrowserSession(result.data.data)
}

export interface TotpStatus { enabled: boolean; available: boolean; recovery_codes_remaining: number }
export interface TotpSetup { secret: string; otpauth_uri: string; expires_at: string }
export interface TotpSession extends LoginResult { recovery_codes?: string[] }
export const totpApi = {
  status: async (signal?: AbortSignal) => (await request.get<ApiResponse<TotpStatus>>('/auth/totp/', { signal })).data.data,
  setup: async (currentPassword: string) => (await request.post<ApiResponse<TotpSetup>>('/auth/totp/setup/', { current_password: currentPassword })).data.data,
  enable: (currentPassword: string, otpCode: string) => change('enable', currentPassword, otpCode),
  disable: (currentPassword: string, otpCode: string) => change('disable', currentPassword, otpCode),
  regenerate: (currentPassword: string, otpCode: string) => change('recovery-codes', currentPassword, otpCode),
}
