import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { post: vi.fn().mockResolvedValue({ data: {} }) } }))
import request from '../src/api/request'
import { usersApi } from '../src/api'
import authApi from '../src/api/auth'

describe('账号密码 API 契约', () => {
  beforeEach(() => { vi.mocked(request.post).mockClear() })
  it('管理员重置默认要求改密，也支持明确关闭', async () => {
    await usersApi.resetPassword('id', 'fixture')
    expect(request.post).toHaveBeenLastCalledWith('/users/id/reset_password/', { password: 'fixture', must_change_password: true })
    await usersApi.resetPassword('id', 'fixture', false)
    expect(request.post).toHaveBeenLastCalledWith('/users/id/reset_password/', { password: 'fixture', must_change_password: false })
  })
  it('自行改密携带旧密码与两次新密码', async () => {
    await authApi.changePassword('old', 'new', 'new')
    expect(request.post).toHaveBeenLastCalledWith('/auth/change_password/', { old_password: 'old', new_password: 'new', new_password2: 'new' })
  })
})
