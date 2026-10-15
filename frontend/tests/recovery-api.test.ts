import { beforeEach, describe, expect, it, vi } from 'vitest'
const publicClient = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), interceptors: { request: { use: vi.fn() } } }))
vi.mock('axios', () => ({ default: { create: vi.fn(() => publicClient) } }))
vi.mock('../src/api/request', () => ({ default: { post: vi.fn() } }))
import request from '../src/api/request'
import authApi from '../src/api/auth'
import { recoveryApi, passwordResetError } from '../src/api/recovery'

describe('公开恢复和认证邮箱验证 API', () => {
  beforeEach(() => { vi.clearAllMocks(); publicClient.get.mockResolvedValue({ data: { data: { enabled: true } } }); publicClient.post.mockResolvedValue({ status: 202 }); vi.mocked(request.post).mockResolvedValue({ status: 202, data: { data: { email_verified: true } } }) })
  it('公开配置只取 enabled，携带取消信号且不使用认证client', async () => {
    const signal = new AbortController().signal
    expect(await recoveryApi.config(signal)).toEqual({ enabled: true })
    expect(publicClient.get).toHaveBeenCalledWith('/auth/recovery/config/', { signal })
    expect(request.post).not.toHaveBeenCalled()
  })
  it('配置结构错误拒绝，而不是误显示入口', async () => {
    publicClient.get.mockResolvedValue({ data: { data: {} } })
    await expect(recoveryApi.config()).rejects.toThrow('Invalid recovery configuration')
  })
  it('申请发送用户名邮箱，202仅代表提交', async () => {
    expect(await recoveryApi.request('member', 'm@example.com')).toBeUndefined()
    expect(publicClient.post).toHaveBeenCalledWith('/auth/recovery/request/', { username: 'member', email: 'm@example.com' })
  })
  it('重置密码只走匿名client并显式发送两次密码', async () => {
    await recoveryApi.reset('isolated-code', 'new', 'new')
    expect(publicClient.post).toHaveBeenCalledWith('/auth/recovery/reset/', { code: 'isolated-code', new_password: 'new', new_password2: 'new' })
    expect(request.post).not.toHaveBeenCalled()
  })
  it('邮箱申请只有当前密码，确认返回资料供调用者更新', async () => {
    await authApi.requestEmailVerification('current')
    expect(request.post).toHaveBeenLastCalledWith('/auth/email-verification/request/', { current_password: 'current' })
    expect(await authApi.confirmEmailVerification('isolated-code')).toEqual({ email_verified: true })
    expect(request.post).toHaveBeenLastCalledWith('/auth/email-verification/confirm/', { code: 'isolated-code' })
  })
  it('密码字段错误只取400的安全字段，不暴露code详情或其他响应', () => {
    expect(passwordResetError({ response: { status: 400, data: { data: { new_password: ['密码过短'] } } } })).toBe('密码过短')
    expect(passwordResetError({ response: { status: 400, data: { data: { code: ['内部详情'] } } } })).toBeUndefined()
    expect(passwordResetError({ response: { status: 500, data: { data: { new_password: ['内部详情'] } } } })).toBeUndefined()
    expect(passwordResetError({ response: { status: 400, data: { data: { new_password2: '两次密码不同' } } } })).toBe('两次密码不同')
  })
})
