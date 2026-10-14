import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), delete: vi.fn(), post: vi.fn() } }))
import request from '../src/api/request'
import { sessionsApi } from '../src/api/sessions'
import { canAccessPage } from '../src/router/access'

describe('会话 API 与访问权限', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const method of [request.get, request.delete, request.post]) vi.mocked(method).mockResolvedValue({ data: { data: { items: [] } } })
  })
  it('本人分页和管理员搜索均支持取消请求', async () => {
    const signal = new AbortController().signal
    await sessionsApi.list(2, 20, signal)
    expect(request.get).toHaveBeenLastCalledWith('/auth/sessions/', { params: { page: 2, page_size: 20 }, signal })
    await sessionsApi.onlineUsers(1, 10, 'member', signal)
    expect(request.get).toHaveBeenLastCalledWith('/auth/online-users/', { params: { page: 1, page_size: 10, search: 'member' }, signal })
  })
  it('撤销设备通过 DELETE body 单次携带当前密码', async () => {
    await sessionsApi.revoke('session-id', 'isolated-password')
    expect(request.delete).toHaveBeenCalledWith('/auth/sessions/session-id/', { data: { current_password: 'isolated-password' } })
  })
  it('全部设备撤销绑定明确用户并单次携带密码', async () => {
    await sessionsApi.revokeAll('user-id', 'isolated-password')
    expect(request.post).toHaveBeenCalledWith('/auth/online-users/user-id/revoke/', { current_password: 'isolated-password' })
  })
  it('本人会话无需管理权限，管理员列表同时需要 staff 身份和读取权限', () => {
    const user = { id: 'member', username: 'member', email: '', avatar: '', permissions: [] as string[] }
    expect(canAccessPage('/settings/sessions', user)).toBe(true)
    expect(canAccessPage('/system/online-users', { ...user, permissions: ['session:read'] })).toBe(false)
    expect(canAccessPage('/system/online-users', { ...user, is_staff: true })).toBe(false)
    expect(canAccessPage('/system/online-users', { ...user, is_staff: true, permissions: ['session:read'] })).toBe(true)
  })
})
