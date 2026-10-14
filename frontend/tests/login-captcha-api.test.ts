import { beforeEach, describe, expect, it, vi } from 'vitest'
const client = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('axios', () => ({ default: { create: vi.fn(() => client) } }))
vi.mock('../src/api/request', () => ({ default: { post: vi.fn() } }))
import request from '../src/api/request'
import authApi from '../src/api/auth'
import { loginCaptchaApi, validateLoginCaptcha } from '../src/api/loginCaptcha'
const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1S8AAAAASUVORK5CYII='
const challenge = { required: true, challenge_id: '00000000-0000-4000-8000-000000000001', image, expires_in: 120 }
describe('登录验证码匿名API及有界PNG契约', () => {
  beforeEach(() => { vi.clearAllMocks(); client.post.mockResolvedValue({ data: { data: challenge } }); vi.mocked(request.post).mockResolvedValue({ data: {} }) })
  it('challenge只发送用户名与abort，不使用认证client', async () => {
    const signal = new AbortController().signal
    expect(await loginCaptchaApi.challenge('member', signal)).toEqual(challenge)
    expect(client.post).toHaveBeenCalledWith('/auth/login-captcha/', { username: 'member' }, { signal })
    expect(request.post).not.toHaveBeenCalled()
    expect(validateLoginCaptcha({ required: false })).toEqual({ required: false })
  })
  it('可选第四参数与MFA并存，只发送明确的captcha字段', async () => {
    await authApi.login('member', 'fixture', '123456', { captcha_id: challenge.challenge_id, captcha_code: 'ABCDE' })
    expect(request.post).toHaveBeenCalledWith('/auth/login/', { username: 'member', password: 'fixture', otp_code: '123456', captcha_id: challenge.challenge_id, captcha_code: 'ABCDE' })
    await authApi.login('member', 'fixture')
    expect(request.post).toHaveBeenLastCalledWith('/auth/login/', { username: 'member', password: 'fixture' })
  })
  it.each([
    { required: 'true' }, { challenge_id: 'unsafe' }, { image: 'data:image/svg+xml;base64,PHN2Zy8+' },
    { image: 'data:image/png;base64,PHN2Zy8+' }, { image: image + '\n' }, { image: 'data:image/png;base64,' + 'A'.repeat(200000) },
    { expires_in: 0 }, { expires_in: 121 }, { expires_in: 0.5 }, { expires_in: '120' },
  ])('拒绝非PNG、无界或非法metadata %j', invalid => { expect(() => validateLoginCaptcha({ ...challenge, ...invalid })).toThrow('Invalid login captcha response') })
})
