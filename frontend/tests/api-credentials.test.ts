import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/request', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
import request from '../src/api/request'
import { apiCredentialsApi } from '../src/api/apiCredentials'

describe('独立开放凭证 API', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(request.get).mockResolvedValue({ data: { data: [] } }); vi.mocked(request.post).mockResolvedValue({ data: { data: {} } }) })
  it('读取本人分页及可用能力，支持中止加载', async () => {
    const signal = new AbortController().signal
    await apiCredentialsApi.list(2, 20, signal)
    expect(request.get).toHaveBeenCalledWith('/api-credentials/credentials/', { params: { page: 2, page_size: 20 }, signal })
    await apiCredentialsApi.scopes(signal)
    expect(request.get).toHaveBeenLastCalledWith('/api-credentials/credentials/scopes/', { signal })
  })
  it('创建使用当前密码确认；撤销使用编码后的本人凭证ID', async () => {
    const draft = { name: 'integration', scopes: ['task:read'], expires_at: '2026-10-20T00:00:00Z' }
    await apiCredentialsApi.create(draft, 'fixture-only')
    expect(request.post).toHaveBeenCalledWith('/api-credentials/credentials/', { ...draft, current_password: 'fixture-only' })
    await apiCredentialsApi.revoke('a/b', 'confirmation')
    expect(request.post).toHaveBeenLastCalledWith('/api-credentials/credentials/a%2Fb/revoke/', { current_password: 'confirmation' })
  })
  it('轮换携带乐观锁版本，统计有界天数且允许取消', async () => {
    await apiCredentialsApi.rotate('a/b', 3, 'confirmation')
    expect(request.post).toHaveBeenLastCalledWith('/api-credentials/credentials/a%2Fb/rotate/', { version: 3, current_password: 'confirmation' })
    const signal = new AbortController().signal
    await apiCredentialsApi.statistics('a/b', 30, signal)
    expect(request.get).toHaveBeenLastCalledWith('/api-credentials/credentials/a%2Fb/statistics/', { params: { days: 30 }, signal })
  })
})
