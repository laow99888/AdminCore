import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('../src/api/publicRequest', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
import request from '../src/api/request'
import publicRequest from '../src/api/publicRequest'
import { ssoApi } from '../src/api/sso'

describe('企业登录公共传输与显式管理', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(publicRequest.get).mockResolvedValue({ data: { data: { enabled: false } } }); vi.mocked(request.post).mockResolvedValue({ data: { data: {} } }) })
  it('公共配置/完成只走不附加 JWT 和自动刷新的传输', async () => {
    const signal = new AbortController().signal
    await ssoApi.config(signal)
    vi.mocked(publicRequest.post).mockResolvedValue({ data: { data: { access: 'fixture-access', refresh: 'fixture-refresh' } } })
    await ssoApi.complete({ otp_code: '123456' }, signal)
    expect(publicRequest.post).toHaveBeenCalledWith('/sso/complete/', { otp_code: '123456' }, { signal })
    expect(request.post).not.toHaveBeenCalled()
    expect(publicRequest.get).toHaveBeenCalledWith('/sso/config/', { signal })
  })
  it('拒绝不安全授权网址；有效 HTTPS 网址由服务端固定供应商', async () => {
    for (const authorization_url of ['javascript:alert(1)', 'https://user:password@idp.example/authorize', 'https://idp.example/authorize#token']) {
      vi.mocked(publicRequest.post).mockResolvedValue({ data: { data: { authorization_url } } })
      await expect(ssoApi.start({})).rejects.toThrow()
    }
    vi.mocked(publicRequest.post).mockResolvedValue({ data: { data: { authorization_url: 'https://idp.example/authorize?state=fixture' } } })
    expect(await ssoApi.start({})).toBe('https://idp.example/authorize?state=fixture')
  })
  it('绑定必须携带管理员密码；撤销使用编码后的 ID', async () => {
    await ssoApi.bind('local-uuid', 'opaque-subject', 'fixture-password')
    expect(request.post).toHaveBeenCalledWith('/sso/identities/', { user_id: 'local-uuid', subject: 'opaque-subject', current_password: 'fixture-password' })
    await ssoApi.unbind('a/b', 'fixture-password')
    expect(request.post).toHaveBeenLastCalledWith('/sso/identities/a%2Fb/unbind/', { current_password: 'fixture-password' })
  })
  it('无效安全校验状态或验证码结构不能展示为可完成状态', async () => {
    vi.mocked(publicRequest.get).mockResolvedValue({ data: { data: { ready: true, mfa_required: 'false', captcha: { required: false } } } })
    await expect(ssoApi.status()).rejects.toThrow()
    vi.mocked(publicRequest.get).mockResolvedValue({ data: { data: { ready: true, mfa_required: false, captcha: { required: true, image: 'javascript:fixture' } } } })
    await expect(ssoApi.status()).rejects.toThrow()
  })
})
