import publicRequest from './publicRequest'
import type { ApiResponse } from './request'

export interface LoginCaptchaProof { captcha_id: string; captcha_code: string }
export type LoginCaptchaChallenge = { required: false } | { required: true; challenge_id: string; image: string; expires_in: number }
// Anonymous challenges do not attach JWTs or enter the authenticated refresh flow.
export function validateLoginCaptcha(value: unknown): LoginCaptchaChallenge {
  const data = value as Partial<Extract<LoginCaptchaChallenge, { required: true }>>
  if ((value as { required?: unknown })?.required === false) return { required: false }
  if (data?.required !== true || typeof data.challenge_id !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(data.challenge_id) ||
    typeof data.image !== 'string' || data.image.length > 200000 || !/^data:image\/png;base64,(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(data.image) ||
    !Number.isInteger(data.expires_in) || data.expires_in! < 1 || data.expires_in! > 120) throw new Error('Invalid login captcha response')
  const png = atob(data.image.slice('data:image/png;base64,'.length))
  if (!png.startsWith('\x89PNG\r\n\x1a\n')) throw new Error('Invalid login captcha response')
  return { required: true, challenge_id: data.challenge_id, image: data.image, expires_in: data.expires_in! }
}
export const loginCaptchaApi = {
  async challenge(username: string, signal?: AbortSignal): Promise<LoginCaptchaChallenge> {
    const response = await publicRequest.post<ApiResponse<unknown>>('/auth/login-captcha/', { username }, { signal })
    return validateLoginCaptcha(response.data.data)
  },
}
