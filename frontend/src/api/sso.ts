import request, { type ApiResponse, type PagedData } from './request'
import publicRequest from './publicRequest'
import type { LoginResult } from './auth'
import { validateLoginCaptcha, type LoginCaptchaChallenge } from './loginCaptcha'

export interface SSOLocalProof { otp_code?: string; captcha_id?: string; captcha_code?: string }
export interface ExternalIdentity {
  id: string; user_id: string; username: string; issuer: string; subject: string
  created_at: string; revoked_at: string | null
}
export const ssoApi = {
  config: async (signal?: AbortSignal) =>
    (await publicRequest.get<ApiResponse<{ enabled: boolean; label?: string }>>('/sso/config/', { signal })).data.data,
  start: async (proof: SSOLocalProof, signal?: AbortSignal) => {
    const data = (await publicRequest.post<ApiResponse<{ authorization_url: string }>>('/sso/start/', proof, { signal })).data.data
    const parsed = new URL(data.authorization_url)
    // The backend pins the provider. A corrupt response must still never navigate to script/data/local schemes.
    if (parsed.protocol !== 'https:' && !(import.meta.env.DEV && parsed.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(parsed.hostname))) throw new Error('Invalid enterprise authorization URL')
    if (parsed.username || parsed.password || parsed.hash) throw new Error('Invalid enterprise authorization URL')
    return parsed.href
  },
  status: async (signal?: AbortSignal): Promise<{ ready: boolean; mfa_required: boolean; captcha: LoginCaptchaChallenge }> => {
    const data = (await publicRequest.get<ApiResponse<{ ready: boolean; mfa_required: boolean; captcha: unknown }>>('/sso/status/', { signal })).data.data
    if (data.ready !== true || typeof data.mfa_required !== 'boolean') throw new Error('Invalid enterprise login response')
    return { ...data, captcha: validateLoginCaptcha(data.captcha) }
  },
  complete: async (proof: SSOLocalProof, signal?: AbortSignal): Promise<LoginResult> =>
    (await publicRequest.post<ApiResponse<LoginResult>>('/sso/complete/', proof, { signal })).data.data,
  cancel: async (signal?: AbortSignal): Promise<void> => { await publicRequest.post('/sso/cancel/', {}, { signal }) },
  list: async (page: number, pageSize: number, signal?: AbortSignal) =>
    (await request.get<ApiResponse<PagedData<ExternalIdentity>>>('/sso/identities/', { params: { page, page_size: pageSize }, signal })).data.data,
  bind: async (userId: string, subject: string, currentPassword: string) =>
    (await request.post<ApiResponse<ExternalIdentity>>('/sso/identities/', { user_id: userId, subject, current_password: currentPassword })).data.data,
  unbind: async (id: string, currentPassword: string) => {
    await request.post(`/sso/identities/${encodeURIComponent(id)}/unbind/`, { current_password: currentPassword })
  },
}
