import { describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
const captures = vi.hoisted(() => ({ request: undefined as ((c: any) => any) | undefined, response: undefined as ((r: any) => any) | undefined, responseError: undefined as ((e: any) => Promise<any>) | undefined, sent: [] as any[], refresh: vi.fn() }))
vi.mock('axios', () => ({ default: { create: () => Object.assign((config: any) => { const next = captures.request!(config); captures.sent.push(next); return Promise.resolve({data: 'replayed'}) }, { interceptors: { request: { use: (handler: any) => { captures.request = handler } }, response: { use: (ok: any, fail: any) => { captures.response = ok; captures.responseError = fail } } } }), isCancel: () => false } }))
vi.mock('../src/router', () => ({ default: { currentRoute: {value:{path:'/business/orders'}}, push: vi.fn() } }))
vi.mock('../src/stores/auth', () => ({ useAuthStore: () => ({clearSession: vi.fn()}) }))
vi.mock('../src/api/tokenRefresh', async original => ({...await original(), refreshSessionTokens: captures.refresh}))
import '../src/api/request'
import { useTenantStore } from '../src/stores/tenants'
const token = (marker: string) => 'fixture.' + btoa(JSON.stringify({sid:'same-session', user_id:'same-user', session_version:1, marker})) + '.fixture'
describe('标签页租户请求与重放隔离', () => {
  it('本标签切换租户后拒绝旧响应和旧请求重放', async () => {
    localStorage.clear(); sessionStorage.clear(); localStorage.setItem('token', token('old')); sessionStorage.setItem('admincore.tenant', 'tenant-A')
    const pending = captures.request!({url:'/business/orders/',headers:{}})
    sessionStorage.setItem('admincore.tenant', 'tenant-B')
    expect(() => captures.response!({config:pending})).toThrow('Tenant changed')
    await expect(captures.responseError!({config:pending,response:{status:401}})).rejects.toMatchObject({__CANCEL__:true})
    expect(() => captures.request!({...pending,_retried:true})).toThrow('Tenant changed')
  })
  it('另一标签的共享偏好不能改写当前标签的请求租户', async () => {
    localStorage.clear(); sessionStorage.clear(); localStorage.setItem('token', token('old')); sessionStorage.setItem('admincore.tenant', 'tenant-A')
    setActivePinia(createPinia()); const tenantA = useTenantStore()
    tenantA.options = [{id:'tenant-A',name:'A',slug:'a',role:'owner'},{id:'tenant-B',name:'B',slug:'b',role:'owner'}]
    tenantA.loaded = true
    const pending = captures.request!({url:'/business/orders/', method:'post',headers:{},data:{name:'created-on-A'}})
    expect(pending.headers['X-AdminCore-Tenant']).toBe('tenant-A')
    localStorage.setItem('admincore.tenant', 'tenant-B')
    window.dispatchEvent(new StorageEvent('storage', {key:'admincore.tenant', oldValue:'tenant-A',newValue:'tenant-B'}))
    expect(tenantA.currentId).toBe('tenant-A')
    const write = captures.request!({url:'/business/orders/',method:'post',headers:{},data:{name:'created-on-A'}})
    expect(write.headers['X-AdminCore-Tenant']).toBe('tenant-A')
    captures.refresh.mockImplementation(async () => {localStorage.setItem('token',token('new'));return {access:token('new'),stale:false}})
    await captures.responseError!({response:{status:401},config:pending})
    expect(captures.sent[0].headers['X-AdminCore-Tenant']).toBe('tenant-A')
    expect(tenantA.currentId).toBe('tenant-A')
  })
})
