import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/request', () => ({ default: { post: vi.fn() } }))
import request from '../src/api/request'
import { usersApi } from '../src/api'
import { userContactPatch } from '../src/utils/userContactPatch'

describe('用户管理敏感字段合同', () => {
  beforeEach(() => vi.clearAllMocks())
  it('本次确认仅向指定用户POST密码且可取消，不缓存到浏览器', async () => {
    const result = { email: 'original@example.test', phone: '13812341234' }, signal = new AbortController().signal
    vi.mocked(request.post).mockResolvedValue({ data: { data: result } })
    expect(await usersApi.sensitive('user-id', 'isolated-password', signal)).toEqual(result)
    expect(request.post).toHaveBeenCalledWith('/users/user-id/sensitive/', { current_password: 'isolated-password' }, { signal })
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain('isolated-password')
  })
  it('编辑留空省略敏感字段，填新值与明确清空电话具有不同语义', () => {
    expect(userContactPatch(' ', '', false)).toEqual({})
    expect(userContactPatch(' new@example.test ', ' 13812341234 ', false)).toEqual({ email: 'new@example.test', phone: '13812341234' })
    expect(userContactPatch('', 'not-submitted', true)).toEqual({ phone: '' })
  })
  it.each([['a***@example.test', ''], ['', '138****1234']])('不把%s %s脱敏字段作为原值提交', (email, phone) => {
    expect(() => userContactPatch(email, phone, false)).toThrow('masked-contact')
  })
})
