import { beforeEach, expect, it, vi } from 'vitest'
const calls = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
vi.mock('../src/api/request', () => ({ default: calls }))
import { featureFlagsApi } from '../src/api/featureFlags'

beforeEach(() => vi.clearAllMocks())
it('创建携带幂等键，更新和删除使用已读版本', async () => {
  const data = { key: 'checkout.new', name: 'new', description: '', enabled: false, rollout: 0, included_users: [], excluded_users: [], roles: [], version: 0 }
  await featureFlagsApi.save('', data, 'fixture-once')
  expect(calls.post).toHaveBeenCalledWith('/feature-flags/flags/', data, { headers: { 'Idempotency-Key': 'fixture-once' } })
  await featureFlagsApi.save('record', { ...data, version: 3 }, 'fixture-once')
  expect(calls.patch).toHaveBeenCalledWith('/feature-flags/flags/record/', { ...data, version: 3 })
  await featureFlagsApi.remove('record', 3)
  expect(calls.delete).toHaveBeenCalledWith('/feature-flags/flags/record/', { data: { version: 3 } })
})
it('读取可中止，评估只传标识，目标查询包含已选值以恢复标签', async () => {
  const signal = new AbortController().signal
  calls.get.mockResolvedValue({ data: { data: [] } }); calls.post.mockResolvedValue({ data: { data: [{ key: 'sample', enabled: true }] } })
  await featureFlagsApi.list({ page: 2, page_size: 20, search: 'sample' }, signal)
  expect(calls.get).toHaveBeenLastCalledWith('/feature-flags/flags/', { params: { page: 2, page_size: 20, search: 'sample' }, signal })
  await featureFlagsApi.detail('record', signal)
  expect(calls.get).toHaveBeenLastCalledWith('/feature-flags/flags/record/', { signal })
  await featureFlagsApi.targets('users', 'name', ['one', 'two'], signal)
  expect(calls.get).toHaveBeenLastCalledWith('/feature-flags/targets/', { params: { kind: 'users', search: 'name', selected: 'one,two' }, signal })
  expect(await featureFlagsApi.evaluate(['sample'], signal)).toEqual([{ key: 'sample', enabled: true }])
  expect(calls.post).toHaveBeenLastCalledWith('/feature-flags/evaluate/', { keys: ['sample'] }, { signal })
})
