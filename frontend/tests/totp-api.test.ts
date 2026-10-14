import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
import request from '../src/api/request'
import authApi from '../src/api/auth'
import { totpApi } from '../src/api/totp'

describe('TOTP API 凭据契约', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(request.get).mockResolvedValue({ data: { data: { enabled: false } } }); vi.mocked(request.post).mockResolvedValue({ data: { data: { recovery_codes: ['fixture'] } } }) })
  it('旧登录不附空otp，双因素登录明确发送otp_code', async () => {
    await authApi.login('member', 'password')
    expect(request.post).toHaveBeenLastCalledWith('/auth/login/', { username: 'member', password: 'password' })
    await authApi.login('member', 'password', '123456')
    expect(request.post).toHaveBeenLastCalledWith('/auth/login/', { username: 'member', password: 'password', otp_code: '123456' })
  })
  it('读取可取消，setup单次发送密码', async () => {
    const signal = new AbortController().signal
    await totpApi.status(signal)
    expect(request.get).toHaveBeenCalledWith('/auth/totp/', { signal })
    await totpApi.setup('password')
    expect(request.post).toHaveBeenLastCalledWith('/auth/totp/setup/', { current_password: 'password' })
  })
  it.each([['enable', '/auth/totp/enable/'], ['disable', '/auth/totp/disable/'], ['regenerate', '/auth/totp/recovery-codes/']] as const)('%s的双重证明明确绑定请求body', async (method, path) => {
    expect(await totpApi[method]('password', '123456')).toEqual({ recovery_codes: ['fixture'] })
    expect(request.post).toHaveBeenLastCalledWith(path, { current_password: 'password', otp_code: '123456' })
  })
})
