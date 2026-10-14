import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
const calls = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
vi.mock('../src/api/request', () => ({ default: calls }))
import { exampleApi, newIdempotencyKey } from '../src/api'
import { canAccessPage } from '../src/router/access'
import { useModuleStore } from '../src/stores/modules'

beforeEach(() => { vi.clearAllMocks(); setActivePinia(createPinia()) })
describe('示例模块声明与API约束', () => {
  it('创建复用显式幂等键，更新与删除携带版本且不提交操作者字段', async () => {
    const data = { title: 'fixture', notes: '', status: 'open' as const, priority: 'normal' as const, version: 0 }
    const key = newIdempotencyKey('example')
    await exampleApi.save('', data, key)
    await exampleApi.save('', data, key)
    expect(calls.post).toHaveBeenNthCalledWith(2, '/example/items/', data, { headers: { 'Idempotency-Key': key } })
    await exampleApi.save('record', { ...data, version: 2 }, key)
    expect(calls.patch).toHaveBeenCalledWith('/example/items/record/', { ...data, version: 2 })
    await exampleApi.remove('record', 2)
    expect(calls.delete).toHaveBeenCalledWith('/example/items/record/', { data: { version: 2 } })
  })
  it('声明的页面权限参与进入、刷新与导航裁剪', () => {
    const user: any = { id: 'fixture', permissions: [] }
    expect(canAccessPage('/example', user, { '/example': 'example:read' })).toBe(false)
    user.permissions = ['example:read']
    expect(canAccessPage('/example', user, { '/example': 'example:read' })).toBe(true)
  })
  it('旧契约可兼容，新声明汇总权限和资源', async () => {
    calls.get.mockResolvedValue({ data: { data: { contract_version: 1, preset: 'minimal', modules: [{ key: 'example', title: 'sample', enabled: false, dependencies: [], paths: ['/example'], page_permissions: { '/example': 'example:read' } }], scope_resources: [{ key: 'example', title: 'sample' }] } } })
    const store = useModuleStore(); await store.load()
    expect(store.pagePermissions).toEqual({ '/example': 'example:read' })
    expect(store.pathEnabled('/example')).toBe(false)
    calls.get.mockResolvedValue({ data: { data: { contract_version: 1, preset: 'minimal', modules: [] } } })
    await store.load(true)
    expect(store.pagePermissions).toEqual({})
    expect(store.pathEnabled('/example')).toBe(false)
    expect(canAccessPage('/example', { id: 'fixture', permissions: [] } as any)).toBe(false)
  })
  it.each([{ '/users': 'example:read' }, { '/example': '*' }, ['bad']])('拒绝越界/非法页面权限声明 %j', async permissions => {
    calls.get.mockResolvedValue({ data: { data: { contract_version: 1, preset: 'standard', modules: [{ key: 'example', title: 'sample', enabled: true, dependencies: [], paths: ['/example'], page_permissions: permissions }] } } })
    const store = useModuleStore()
    await expect(store.load()).rejects.toThrow()
    expect(store.config).toBeNull()
  })
})
