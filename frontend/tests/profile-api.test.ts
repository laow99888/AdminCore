import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
import request from '../src/api/request'
import authApi from '../src/api/auth'

describe('个人资料和头像 API 契约', () => {
  beforeEach(() => { vi.clearAllMocks() })
  it('只发送资料白名单与版本，解包服务端结果', async () => {
    const data = { first_name: 'name', last_name: '', email: 'a@example.com', phone: '', bio: '', profile_version: 3 }
    vi.mocked(request.patch).mockResolvedValue({ data: { data: { ...data, profile_version: 4 } } })
    expect((await authApi.saveProfile(data)).profile_version).toBe(4)
    expect(request.patch).toHaveBeenCalledWith('/auth/profile/', data)
  })
  it('上传使用 multipart 及版本，删除版本使用 JSON 请求体', async () => {
    vi.mocked(request.post).mockResolvedValue({ data: { data: {} } })
    vi.mocked(request.delete).mockResolvedValue({ data: { data: {} } })
    const file = new File(['image'], 'avatar.png')
    await authApi.uploadAvatar(file, 5)
    const body = vi.mocked(request.post).mock.calls[0]![1] as FormData
    expect(body.get('file')).toBe(file)
    expect(body.get('profile_version')).toBe('5')
    await authApi.removeAvatar(6)
    expect(request.delete).toHaveBeenCalledWith('/auth/avatar/', { data: { profile_version: 6 } })
  })
  it('鉴权图片使用 Blob 请求和取消信号，拒绝异常响应', async () => {
    const signal = new AbortController().signal
    const blob = new Blob(['png'], { type: 'image/png' })
    vi.mocked(request.get).mockResolvedValue({ data: blob })
    expect(await authApi.avatar(signal)).toBe(blob)
    expect(request.get).toHaveBeenCalledWith('/auth/avatar/', { responseType: 'blob', signal })
    for (const bad of [new Blob([]), new Blob(['html'], { type: 'text/html' }), new Blob([new Uint8Array(1024 * 1024 + 1)], { type: 'image/png' })]) {
      vi.mocked(request.get).mockResolvedValue({ data: bad })
      await expect(authApi.avatar(signal)).rejects.toThrow('Invalid avatar response')
    }
  })
})
